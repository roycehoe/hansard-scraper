import argparse

from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.seat_holding import CRUDSeatHolding
from database.init import engine
from database.seat_holding import SeatHolding
from logs import logger
from populate.seat_holdings import (
    SeatHoldingPlan,
    get_seat_holding_plan,
    write_seat_holding_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write


def _log_plan(plan: SeatHoldingPlan) -> None:
    logger.info(
        f"Plan: {len(plan.seat_holdings_to_add):,} seat holdings to add,"
        f" {len(plan.seat_holding_updates):,} to update,"
        f" {len(plan.seat_holding_ids_to_delete):,} to delete"
    )
    for decade, seat_holding_count in sorted(plan.decade_to_count.items()):
        logger.info(f"{decade}s: {seat_holding_count:,} seat holdings")


def apply_seat_holdings(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        speaker_ids = sorted(
            set(
                CRUDAttendance(
                    session
                ).get_distinct_speaker_ids_by_speaker_id_not_null()
            )
            | set(CRUDSeatHolding(session).get_distinct_speaker_ids())
        )
        plan = get_seat_holding_plan(session, speaker_ids)
        _log_plan(plan)
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_seat_holding_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [SeatHolding.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store each Member's seat holdings, built from the attendance rows"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored counts by decade against the plan; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_seat_holdings(arguments.commit)
