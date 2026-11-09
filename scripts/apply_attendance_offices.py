import argparse
from collections import Counter

from sqlmodel import Session

from crud.office_printed_range import CRUDOfficePrintedRange
from crud.sitting import CRUDSitting
from database.attendance_office import AttendanceOffice
from database.init import engine
from database.office_printed_range import OfficePrintedRange
from logs import logger
from populate.attendance_offices import (
    AttendanceOfficePlan,
    get_attendance_office_plan,
    write_attendance_office_plan,
)
from populate.office_printed_ranges import (
    OfficePrintedRangePlan,
    get_office_printed_range_plan,
    write_office_printed_range_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write


def _format_row_counts(key_to_row_count: Counter) -> str:
    return (
        ", ".join(
            f"{key} {row_count:,}"
            for key, row_count in sorted(key_to_row_count.items())
        )
        or "none"
    )


def _log_attendance_office_plan(plan: AttendanceOfficePlan) -> None:
    logger.info(
        f"Plan: {len(plan.attendance_offices):,} attendance offices for {len(plan.sitting_ids):,} sittings;"
        f" by decade: {_format_row_counts(plan.decade_to_row_count)};"
        f" by source: {_format_row_counts(plan.source_to_row_count)};"
        f" {plan.entries_without_attendance_row:,} entries with no attendance row;"
        f" {plan.duplicate_entries:,} duplicate entries"
    )


def _log_office_printed_range_plan(
    deleted_range_count: int, plan: OfficePrintedRangePlan
) -> None:
    logger.info(
        f"Office printed ranges: deleted {deleted_range_count:,}, plan {len(plan.office_printed_ranges):,};"
        f" by decade: {_format_row_counts(plan.decade_to_row_count)};"
        f" {plan.rows_without_speaker_id:,} stored offices with no speaker_id"
    )


def apply_attendance_offices(sitting_ids: list[int], is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        attendance_office_plan = get_attendance_office_plan(
            session,
            sitting_ids
            or [
                sitting_date_row.id
                for sitting_date_row in CRUDSitting(session).get_date_rows()
            ],
        )
        _log_attendance_office_plan(attendance_office_plan)
        if not is_commit:
            logger.info(
                "Dry run: nothing written. Ranges are built from the stored rows during a commit"
            )
            return

        deleted_range_count = CRUDOfficePrintedRange(session).delete_all()
        write_attendance_office_plan(session, attendance_office_plan)
        office_printed_range_plan = get_office_printed_range_plan(session)
        _log_office_printed_range_plan(deleted_range_count, office_printed_range_plan)
        write_office_printed_range_plan(session, office_printed_range_plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session,
            [AttendanceOffice.__tablename__, OfficePrintedRange.__tablename__],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the printed office of each attendance entry and build the printed office ranges from them"
    )
    parser.add_argument(
        "--sitting-id",
        type=int,
        nargs="+",
        action="extend",
        default=[],
        help="only these sittings' offices; the ranges are rebuilt in full either way; without it every sitting",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored counts against the plan; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_attendance_offices(arguments.sitting_id, arguments.commit)
