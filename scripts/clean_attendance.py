import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.attendance import AttendanceSpeakerRow, CRUDAttendance
from crud.sitting import CRUDSitting, SittingDateRow
from crud.speaker import CRUDSpeaker
from database.attendance import Attendance
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.attendance_cleanup import AttendanceCleanup
from services.attendance import build_speaker_lookups
from services.attendance_cleanup import (
    AttendanceCleanupPlan,
    build_attendance_cleanup_plan,
)
from services.speaker_link import resolve_attendance_rows
from settings import settings
from utils.sitting_dates import parse_sitting_date
from utils.speaker_terms import SPEAKER_TERMS
from utils.write_target import validate_can_write

_ATTENDANCE_CLEANUP_FILE = Path(__file__).parent.parent / "data" / "attendance_cleanup.json"


def _get_presiding_officer_name(sitting_date: str) -> Optional[str]:
    day = parse_sitting_date(sitting_date).date()
    names = [name for first, last, name in SPEAKER_TERMS if first <= day <= last]
    return names[0] if len(names) == 1 else None


def _get_name_row(attendance_id: int, speaker_name: str, sitting: SittingDateRow) -> AttendanceSpeakerRow:
    return AttendanceSpeakerRow(attendance_id, speaker_name, sitting.parlement_no, sitting.volume_no)


def _get_plan(session: Session, cleanup: AttendanceCleanup, id_to_row: dict[int, Attendance]) -> AttendanceCleanupPlan:
    speakers = CRUDSpeaker(session).get_all()
    sitting_id_to_sitting = {sitting.id: sitting for sitting in CRUDSitting(session).get_date_rows()}
    name_rows = [
        _get_name_row(correction.id, correction.speaker_name_after, sitting_id_to_sitting[correction.sitting_id])
        for correction in cleanup.corrections
    ]
    for role in cleanup.speaker_roles:
        presiding_officer_name = _get_presiding_officer_name(role.sitting_date)
        if presiding_officer_name is not None:
            name_rows.append(_get_name_row(role.id, presiding_officer_name, sitting_id_to_sitting[role.sitting_id]))
    role_sitting_ids = sorted({role.sitting_id for role in cleanup.speaker_roles})
    sitting_id_to_rows: dict[int, list[Attendance]] = {sitting_id: [] for sitting_id in role_sitting_ids}
    for row in CRUDAttendance(session).get_by_sitting_ids(role_sitting_ids):
        sitting_id_to_rows[row.sitting_id].append(row)
    resolved_speaker_ids = resolve_attendance_rows(
        name_rows,
        build_speaker_lookups(speakers),
        {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers if speaker.id is not None},
    )
    logger.info(f"Attendance: set speaker_id on {len(resolved_speaker_ids.id_to_speaker_id)}/{resolved_speaker_ids.row_count} records")
    speaker_id_to_name = {speaker.id: speaker.name for speaker in speakers if speaker.id is not None}
    return build_attendance_cleanup_plan(cleanup, id_to_row, sitting_id_to_rows, resolved_speaker_ids.id_to_speaker_id, speaker_id_to_name)


def _validate_written(session: Session, plan: AttendanceCleanupPlan, linked_pairs_removed: set[tuple[int, int]]) -> None:
    session.expire_all()
    removed_ids_still_stored = [row.id for row in CRUDAttendance(session).get_by_ids(list(plan.removal_id_to_reason))]
    if removed_ids_still_stored:
        raise HansardWriteCheckError(f"Attendance rows still stored after the delete: {sorted(removed_ids_still_stored)}")
    update_id_to_update = {update.id: update for update in plan.updates}
    for row in CRUDAttendance(session).get_by_ids(list(update_id_to_update)):
        update = update_id_to_update[row.id]
        if (row.speaker_name, row.location_name, row.speaker_id) != (update.speaker_name, update.location_name, update.speaker_id):
            raise HansardWriteCheckError(f"Attendance row {row.id} does not hold the planned values after the update")
    pair_to_count = Counter((row.sitting_id, row.speaker_id) for row in CRUDAttendance(session).get_presence_rows_by_speaker_id_not_null())
    repeated_pairs = sorted(pair for pair, count in pair_to_count.items() if count > 1)
    if repeated_pairs:
        raise HansardWriteCheckError(f"Attendance rows repeat a speaker within a sitting after the cleanup: {repeated_pairs}")
    emptied_pairs = sorted(pair for pair in linked_pairs_removed if pair not in pair_to_count)
    if emptied_pairs:
        raise HansardWriteCheckError(f"The cleanup removed the only row of a speaker in a sitting: {emptied_pairs}")


def _apply_plan(session: Session, plan: AttendanceCleanupPlan, id_to_row: dict[int, Attendance]) -> None:
    linked_pairs_removed = {
        (id_to_row[removal_id].sitting_id, id_to_row[removal_id].speaker_id)
        for removal_id in plan.removal_id_to_reason
        if id_to_row[removal_id].speaker_id is not None
    }
    deleted_count = CRUDAttendance(session).delete_by_ids(list(plan.removal_id_to_reason))
    if deleted_count != len(plan.removal_id_to_reason):
        raise HansardWriteCheckError(f"Deleted {deleted_count} attendance rows, planned {len(plan.removal_id_to_reason)}")
    for update in plan.updates:
        row = id_to_row[update.id]
        row.speaker_name = update.speaker_name
        row.location_name = update.location_name
        row.speaker_id = update.speaker_id
    CRUDAttendance(session).update_many([id_to_row[update.id] for update in plan.updates])
    _validate_written(session, plan, linked_pairs_removed)


def _log_plan(plan: AttendanceCleanupPlan, unlinked_before: int, unlinked_after: int) -> None:
    for reason, count in sorted(Counter(plan.removal_id_to_reason.values()).items()):
        logger.info(f"Delete {count} rows: {reason}")
    for reason, count in sorted(Counter(update.reason for update in plan.updates).items()):
        logger.info(f"Update and link {count} rows: {reason}")
    logger.info(
        f"Plan: delete {len(plan.removal_id_to_reason)} rows, update {len(plan.updates)} rows; "
        f"unlinked rows {unlinked_before} before, {unlinked_after} after"
    )


def clean_attendance(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    cleanup = AttendanceCleanup.model_validate(json.loads(_ATTENDANCE_CLEANUP_FILE.read_text()))
    entry_ids = [entry.id for entry in (*cleanup.removals, *cleanup.corrections, *cleanup.speaker_roles)]
    with Session(engine) as session:
        id_to_row = {row.id: row for row in CRUDAttendance(session).get_by_ids(entry_ids) if row.id is not None}
        unlinked_before = len(CRUDAttendance(session).get_speaker_rows_by_speaker_id_null())
        plan = _get_plan(session, cleanup, id_to_row)
        removed_unlinked_count = sum(id_to_row[removal_id].speaker_id is None for removal_id in plan.removal_id_to_reason)
        unlinked_after = unlinked_before - removed_unlinked_count - len(plan.updates)
        _log_plan(plan, unlinked_before, unlinked_after)
        if plan_path is not None:
            plan_path.write_text(
                json.dumps({"removal_id_to_reason": plan.removal_id_to_reason, "updates": [asdict(update) for update in plan.updates]}, indent=1)
            )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _apply_plan(session, plan, id_to_row)
        if len(CRUDAttendance(session).get_speaker_rows_by_speaker_id_null()) != unlinked_after:
            raise HansardWriteCheckError(f"Unlinked attendance rows are not {unlinked_after} after the cleanup")
        session.commit()
        logger.info(f"Committed: {len(plan.removal_id_to_reason)} rows deleted, {len(plan.updates)} rows updated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean the stored attendance rows named in data/attendance_cleanup.json")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    clean_attendance(arguments.commit, arguments.plan)
