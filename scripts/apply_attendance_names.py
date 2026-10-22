import argparse
import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.attendance import AttendanceSpeakerRow, CRUDAttendance
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from database.attendance import Attendance
from database.init import engine
from database.speaker import Speaker
from exceptions import HansardWriteCheckError
from logs import logger
from services.attendance import (
    AttendanceNameChange,
    build_constituency_lookups,
    build_sitting_attendances,
    build_speaker_lookups,
    get_attendance_name_changes,
)
from services.speaker_link import resolve_attendance_rows
from settings import settings
from utils.data_files import get_constituency_names
from utils.speaker_resolution import SpeakerLookups
from utils.write_target import validate_can_write


def _validate_can_keep_speaker_ids(
    name_changes: list[AttendanceNameChange], speaker_rows: list[AttendanceSpeakerRow], speakers: list[Speaker], lookups: SpeakerLookups
) -> None:
    resolved_speaker_ids = resolve_attendance_rows(
        speaker_rows, lookups, {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None}
    )
    logger.info(f"Attendance: set speaker_id on {len(resolved_speaker_ids.id_to_speaker_id)}/{resolved_speaker_ids.row_count} records")
    for name_change in name_changes:
        if resolved_speaker_ids.id_to_speaker_id.get(name_change.id) != name_change.speaker_id:
            raise HansardWriteCheckError(
                f"Attendance row {name_change.id}: speaker {name_change.speaker_id}, stage 8 links {name_change.speaker_name_after!r} "
                f"to {resolved_speaker_ids.id_to_speaker_id.get(name_change.id)}"
            )


def _get_planned_changes(session: Session) -> list[AttendanceNameChange]:
    speakers = CRUDSpeaker(session).get_all()
    lookups = build_speaker_lookups(speakers)
    constituency_lookups = build_constituency_lookups(get_constituency_names())
    sitting_id_to_attendances: dict[int, list[Attendance]] = defaultdict(list)
    for attendance in CRUDAttendance(session).get_all():
        sitting_id_to_attendances[attendance.sitting_id].append(attendance)
    name_changes = []
    speaker_rows = []
    for sitting in CRUDSitting(session).get_all():
        sitting_name_changes = get_attendance_name_changes(
            sitting.id, sitting_id_to_attendances[sitting.id], build_sitting_attendances(sitting, lookups, constituency_lookups)
        )
        name_changes.extend(sitting_name_changes)
        speaker_rows.extend(
            AttendanceSpeakerRow(name_change.id, name_change.speaker_name_after, sitting.parlement_no, sitting.volume_no)
            for name_change in sitting_name_changes
        )
    _validate_can_keep_speaker_ids(name_changes, speaker_rows, speakers, lookups)
    return name_changes


def _get_planned_row(name_change: AttendanceNameChange, speaker_name: Optional[str]) -> Attendance:
    return Attendance(
        id=name_change.id, sitting_id=name_change.sitting_id, speaker_name=speaker_name, is_present=name_change.is_present,
        location_name=name_change.location_name, speaker_id=name_change.speaker_id,
    )


def _validate_can_commit_attendances(session: Session, planned_rows: list[Attendance]) -> None:
    id_to_planned_row = {planned_row.id: planned_row for planned_row in planned_rows}
    attendances = CRUDAttendance(session).get_by_ids_for_update(list(id_to_planned_row))
    if len(attendances) != len(planned_rows):
        raise HansardWriteCheckError(f"{len(attendances)} of {len(planned_rows)} planned attendance rows are stored")
    for attendance in attendances:
        if attendance.model_dump() != id_to_planned_row[attendance.id].model_dump():
            raise HansardWriteCheckError(f"Attendance row {attendance.id} holds {attendance.model_dump()}, planned {id_to_planned_row[attendance.id].model_dump()}")


def _get_row_count(session: Session) -> int:
    return sum(sitting_count.row_count for sitting_count in CRUDAttendance(session).get_sitting_counts())


def apply_attendance_names(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        name_changes = _get_planned_changes(session)
        pair_to_count = Counter((name_change.speaker_name_before, name_change.speaker_name_after) for name_change in name_changes)
        for (speaker_name_before, speaker_name_after), count in sorted(pair_to_count.items(), key=lambda item: (-item[1], str(item[0]))):
            logger.info(f"{count} rows: {speaker_name_before!r} -> {speaker_name_after!r}")
        logger.info(f"Plan: {len(name_changes)} name changes in {len(pair_to_count)} spellings")
        if plan_path is not None:
            plan_path.write_text(json.dumps([asdict(name_change) for name_change in name_changes], indent=1, ensure_ascii=False))
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        row_count_before = _get_row_count(session)
        session.expire_all()
        _validate_can_commit_attendances(session, [_get_planned_row(name_change, name_change.speaker_name_before) for name_change in name_changes])
        updated_count = CRUDAttendance(session).set_speaker_names_bulk(
            {name_change.id: name_change.speaker_name_after for name_change in name_changes}
        )
        if updated_count != len(name_changes):
            raise HansardWriteCheckError(f"Updated {updated_count} attendance rows, planned {len(name_changes)}")
        session.expire_all()
        _validate_can_commit_attendances(session, [_get_planned_row(name_change, name_change.speaker_name_after) for name_change in name_changes])
        if _get_row_count(session) != row_count_before:
            raise HansardWriteCheckError("The attendance row count changed during the update")
        session.commit()
        logger.info(f"Committed: {len(name_changes)} name changes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set stored attendance names to the names stage 7 builds, where nothing else differs")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    apply_attendance_names(arguments.commit, arguments.plan)
