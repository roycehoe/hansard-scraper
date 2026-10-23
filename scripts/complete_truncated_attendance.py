import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from sqlmodel import Session

from crud.attendance import AttendanceSpeakerRow, CRUDAttendance
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from database.attendance import Attendance
from database.init import engine
from database.sitting import Sitting
from exceptions import HansardWriteCheckError
from logs import logger
from populate.written_tables import vacuum_analyze_written_tables
from schemas.attendance_completion_plan import (
    AttendanceCompletionPlan,
    PlannedAttendance,
    SittingAttendanceCompletion,
)
from services.attendance import (
    build_constituency_lookups,
    build_sitting_attendances_from_markdown,
    build_speaker_lookups,
)
from services.speaker_link import resolve_attendance_rows
from settings import settings
from utils.data_files import get_constituency_names
from utils.write_target import validate_can_write

_SITTING_DATE_CHUNK = 100


def get_rows_to_insert(sitting_id: int, stored_rows: list[Attendance], built_rows: list[Attendance]) -> list[Attendance]:
    stored_key_to_unmatched_count = Counter((stored_row.speaker_name, stored_row.is_present, stored_row.location_name) for stored_row in stored_rows)
    rows_to_insert = []
    for built_row in built_rows:
        built_key = (built_row.speaker_name, built_row.is_present, built_row.location_name)
        if stored_key_to_unmatched_count[built_key] > 0:
            stored_key_to_unmatched_count[built_key] -= 1
            continue
        rows_to_insert.append(built_row)
    stored_keys_not_built = list(stored_key_to_unmatched_count.elements())
    if stored_keys_not_built:
        raise HansardWriteCheckError(f"Sitting {sitting_id}: {len(stored_keys_not_built)} stored rows are not built by stage 7, first {stored_keys_not_built[0]}")
    return rows_to_insert


def validate_can_plan_speaker_ids(sitting_id: int, stored_rows: list[Attendance], planned_rows: list[PlannedAttendance]) -> None:
    stored_speaker_ids = [stored_row.speaker_id for stored_row in stored_rows if stored_row.speaker_id is not None]
    planned_speaker_ids = [planned_row.speaker_id for planned_row in planned_rows if planned_row.speaker_id is not None]
    speaker_ids = stored_speaker_ids + planned_speaker_ids
    if len(set(speaker_ids)) != len(speaker_ids):
        raise HansardWriteCheckError(f"Sitting {sitting_id}: a planned row repeats a speaker already in the sitting")


def _get_plan(session: Session) -> AttendanceCompletionPlan:
    speakers = CRUDSpeaker(session).get_all()
    lookups = build_speaker_lookups(speakers)
    constituency_lookups = build_constituency_lookups(get_constituency_names())
    name_parliament_number_to_speaker_id = {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None}
    sitting_id_to_stored_rows = defaultdict(list)
    for stored_row in CRUDAttendance(session).get_all():
        sitting_id_to_stored_rows[stored_row.sitting_id].append(stored_row)
    date_rows = sorted(
        (date_row for date_row in CRUDSitting(session).get_date_rows() if date_row.id in sitting_id_to_stored_rows),
        key=lambda date_row: date_row.id,
    )
    sitting_dates = [date_row.sitting_date for date_row in date_rows]
    if len(set(sitting_dates)) != len(sitting_dates):
        raise HansardWriteCheckError("Two sittings with attendance rows share a date")

    sitting_date_to_markdown = {}
    for chunk_start in range(0, len(sitting_dates), _SITTING_DATE_CHUNK):
        for date_markdown_row in CRUDSitting(session).get_date_markdown_rows_by_sitting_dates_and_markdown_content_not_null(sitting_dates[chunk_start : chunk_start + _SITTING_DATE_CHUNK]):
            sitting_date_to_markdown[date_markdown_row.sitting_date] = date_markdown_row.markdown_content

    sittings = []
    for date_row in date_rows:
        markdown = sitting_date_to_markdown.get(date_row.sitting_date)
        if markdown is None:
            continue
        stored_rows = sitting_id_to_stored_rows[date_row.id]
        sitting = Sitting(id=date_row.id, sitting_date=date_row.sitting_date, markdown_content=markdown, parlement_no=date_row.parlement_no, volume_no=date_row.volume_no)
        built_rows = build_sitting_attendances_from_markdown(sitting, lookups, constituency_lookups)
        if len(built_rows) <= len(stored_rows):
            continue
        rows_to_insert = get_rows_to_insert(date_row.id, stored_rows, built_rows)
        attendance_speaker_rows = [
            AttendanceSpeakerRow(id=index, speaker_name=row_to_insert.speaker_name, parlement_no=date_row.parlement_no, volume_no=date_row.volume_no)
            for index, row_to_insert in enumerate(rows_to_insert)
        ]
        index_to_speaker_id = resolve_attendance_rows(attendance_speaker_rows, lookups, name_parliament_number_to_speaker_id).id_to_speaker_id
        planned_rows = [
            PlannedAttendance(
                speaker_name=row_to_insert.speaker_name,
                is_present=row_to_insert.is_present,
                location_name=row_to_insert.location_name,
                speaker_id=index_to_speaker_id.get(index),
            )
            for index, row_to_insert in enumerate(rows_to_insert)
        ]
        validate_can_plan_speaker_ids(date_row.id, stored_rows, planned_rows)
        sittings.append(SittingAttendanceCompletion(
            sitting_id=date_row.id,
            sitting_date=date_row.sitting_date,
            markdown_md5=hashlib.md5(markdown.encode("utf-8")).hexdigest(),
            stored_row_count=len(stored_rows),
            built_row_count=len(built_rows),
            rows_to_insert=planned_rows,
        ))
    plan = AttendanceCompletionPlan(sittings=sittings)
    row_count = sum(len(sitting.rows_to_insert) for sitting in plan.sittings)
    linked_count = sum(planned_row.speaker_id is not None for sitting in plan.sittings for planned_row in sitting.rows_to_insert)
    logger.info(f"Plan: {len(plan.sittings)} sittings, insert {row_count} attendance rows, {linked_count} linked")
    return plan


def _read_plan(plan_path: Path) -> AttendanceCompletionPlan:
    return AttendanceCompletionPlan.model_validate_json(plan_path.read_text())


def _validate_can_commit_sitting_counts(session: Session, plan: AttendanceCompletionPlan) -> None:
    sitting_id_to_row_count = {count.sitting_id: count.row_count for count in CRUDAttendance(session).get_sitting_counts()}
    for sitting in plan.sittings:
        row_count = sitting_id_to_row_count.get(sitting.sitting_id, 0)
        if row_count != sitting.built_row_count:
            raise HansardWriteCheckError(f"Sitting {sitting.sitting_id}: {row_count} rows after the write, expected {sitting.built_row_count}")


def complete_truncated_attendance(plan_path: Path, is_commit: bool) -> None:
    if not is_commit:
        with Session(engine) as session:
            plan = _get_plan(session)
        plan_path.write_text(json.dumps(plan.model_dump(), indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = _read_plan(plan_path)
    with Session(engine) as session:
        plan = _get_plan(session)
        if plan != reviewed_plan:
            raise HansardWriteCheckError("The plan differs from the reviewed plan")
        attendances_to_insert = [
            Attendance(
                sitting_id=sitting.sitting_id,
                speaker_name=planned_row.speaker_name,
                is_present=planned_row.is_present,
                location_name=planned_row.location_name,
                speaker_id=planned_row.speaker_id,
            )
            for sitting in plan.sittings
            for planned_row in sitting.rows_to_insert
        ]
        CRUDAttendance(session).add_many(attendances_to_insert)
        _validate_can_commit_sitting_counts(session, plan)
        session.commit()
        vacuum_analyze_written_tables(session, [Attendance.__tablename__])
    logger.info(f"Committed: {len(attendances_to_insert)} attendance rows in {len(plan.sittings)} sittings")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Insert the attendance rows stage 7 builds and a sitting lacks, checked against a reviewed plan")
    parser.add_argument("plan", type=Path, help="the plan file: written by a dry run, read by --commit")
    parser.add_argument("--commit", action="store_true", help="build the plan again, refuse unless it equals the reviewed file, and write it")
    arguments = parser.parse_args()
    complete_truncated_attendance(arguments.plan, arguments.commit)
