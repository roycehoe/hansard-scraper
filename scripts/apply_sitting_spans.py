import argparse

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.sitting_span import CRUDSittingSpan
from database.init import engine
from database.sitting_span import SittingSpan
from logs import logger
from populate.sitting_spans import (
    SittingSpanPlan,
    get_sitting_span_plan,
    write_sitting_span_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write


def _log_plan(plan: SittingSpanPlan) -> None:
    logger.info(
        f"Plan: {len(plan.sitting_spans_to_add):,} sitting spans to add,"
        f" {len(plan.sitting_span_updates):,} to update,"
        f" {len(plan.sitting_span_ids_to_delete):,} to delete"
    )
    for decade, sitting_span_count in sorted(plan.decade_to_count.items()):
        logger.info(f"{decade}s: {sitting_span_count:,} sitting spans")


def apply_sitting_spans(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        if is_commit:
            # NOTE: locked before the plan is read, so a row the daily job widens is in the plan or waits
            CRUDSittingSpan(session).lock_table_in_share_row_exclusive_mode()
        speaker_ids = sorted(
            set(
                CRUDAttendance(
                    session
                ).get_distinct_speaker_ids_by_speaker_id_not_null()
            )
            | set(CRUDSittingSpan(session).get_distinct_speaker_ids())
        )
        plan = get_sitting_span_plan(session, speaker_ids)
        _log_plan(plan)
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_sitting_span_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [SittingSpan.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store each membership's first and last listed sitting, built from the attendance rows"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored counts by decade against the plan; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_sitting_spans(arguments.commit)
