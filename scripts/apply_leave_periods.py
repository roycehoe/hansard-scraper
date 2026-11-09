import argparse
from collections import Counter

from sqlmodel import Session

from crud.sitting import CRUDSitting
from database.init import engine
from database.leave_period import LeavePeriod, LeavePeriodPrinting
from logs import logger
from populate.leave_periods import (
    PlannedLeavePrinting,
    get_leave_period_plan,
    write_leave_period_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write


def _log_counts(label: str, value_to_count: Counter) -> None:
    logger.info(
        f"{label}: "
        + ", ".join(
            f"{value} {count:,}"
            for value, count in sorted(value_to_count.items(), key=str)
        )
    )


def _log_plan(planned_printings: list[PlannedLeavePrinting]) -> None:
    logger.info(
        f"Plan: {len(planned_printings):,} printings in"
        f" {len({planned_printing.period_key for planned_printing in planned_printings}):,} periods"
    )
    _log_counts(
        "By entry format",
        Counter(
            planned_printing.leave_entry.entry_format
            for planned_printing in planned_printings
        ),
    )
    _log_counts(
        "By name source",
        Counter(
            planned_printing.leave_entry.name_source
            for planned_printing in planned_printings
        ),
    )
    _log_counts(
        "By year source",
        Counter(
            planned_printing.leave_entry.year_source
            for planned_printing in planned_printings
        ),
    )
    _log_counts(
        "By link source",
        Counter(
            None
            if planned_printing.speaker_link is None
            else planned_printing.speaker_link.speaker_link_source
            for planned_printing in planned_printings
        ),
    )


def apply_leave_periods(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        planned_printings = get_leave_period_plan(
            session,
            [
                sitting_date_row.id
                for sitting_date_row in CRUDSitting(session).get_date_rows()
            ],
        )
        _log_plan(planned_printings)
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_leave_period_plan(session, planned_printings)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session, [LeavePeriod.__tablename__, LeavePeriodPrinting.__tablename__]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store each leave period and its printings, read from the permission lists"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored counts against the plan; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_leave_periods(arguments.commit)
