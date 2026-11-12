import argparse

from sqlmodel import Session

from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write

_RAW_TABLE_NAME = "hansardsittingdateresponse"


def copy_sitting_lists_to_raw(is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        crud_raw = CRUDHansardSittingDateResponse(session)
        crud_raw.lock_table_in_share_row_exclusive_mode()
        plan = crud_raw.get_fill_counts_by_sitting_sitting_date_and_lists_null()
        logger.info(
            f"Plan: {plan.rows} raw rows to fill from sitting (sections {plan.sections}, "
            f"annexures {plan.annexures}, vernaculars {plan.vernaculars}, a2b {plan.a2b})"
        )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        written = crud_raw.set_sections_annexures_vernaculars_and_a2b_from_sitting_by_sitting_date()
        if written != plan.rows:
            raise HansardWriteCheckError(
                f"Updated {written} raw rows, planned {plan.rows}"
            )
        left = crud_raw.get_fill_counts_by_sitting_sitting_date_and_lists_null()
        if left.rows != 0:
            raise HansardWriteCheckError(
                f"{left.rows} raw rows are still to fill after the update"
            )
        session.commit()
        logger.info(f"Committed: {written} raw rows filled")
        vacuum_analyze_written_tables(session, [_RAW_TABLE_NAME])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Copy the sections, annexures, vernaculars and a2b lists from sitting to the raw sitting table; no request to SPRS, a rerun writes nothing"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    copy_sitting_lists_to_raw(arguments.commit)
