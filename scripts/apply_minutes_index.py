import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.minutes import CRUDMinutes
from crud.minutes_index_capture import CRUDMinutesIndexCapture
from database.init import engine
from database.minutes import Minutes, MinutesIndexCapture
from enums import MinutesStatus
from exceptions import HansardWriteCheckError
from logs import logger
from populate.minutes_index import get_minutes_index_plan, write_minutes_index_plan
from populate.written_tables import vacuum_analyze_written_tables
from schemas.minutes_index_plan import MinutesIndexPlan
from settings import settings
from utils.write_target import validate_can_write


def _log_plan(plan: MinutesIndexPlan) -> None:
    logger.info(f"Captures: {len(plan.captures):,}")
    for planned_capture in plan.captures:
        logger.info(
            f"Capture {planned_capture.file}: {planned_capture.row_count:,} rows"
        )
    new_count = sum(planned_row.is_new_row for planned_row in plan.rows)
    status_to_moved_count = Counter(
        planned_row.expected_status
        for planned_row in plan.rows
        if not planned_row.is_new_row
    )
    logger.info(
        f"Rows: {new_count:,} new, {status_to_moved_count[MinutesStatus.NOT_YET_LISTED]:,} moved from NOT_YET_LISTED, {status_to_moved_count[MinutesStatus.FILE_NOT_FOUND]:,} moved from FILE_NOT_FOUND, {plan.stored_row_count:,} already stored"
    )
    status_to_count = Counter(planned_row.status.value for planned_row in plan.rows)
    logger.info(
        f"Rows by status: {', '.join(f'{status} {count:,}' for status, count in sorted(status_to_count.items()))}"
    )
    index_source_to_count = Counter(
        planned_row.index_source.value
        for planned_row in plan.rows
        if planned_row.index_source is not None
    )
    logger.info(
        f"Rows by index source: {', '.join(f'{index_source} {count:,}' for index_source, count in sorted(index_source_to_count.items()))}"
    )
    logger.info(
        f"Duplicates dropped: {plan.duplicate_count:,}, conflicting addresses: {plan.conflicting_address_count:,}"
    )


def _validate_can_commit_minutes_index(
    session: Session, plan: MinutesIndexPlan
) -> None:
    stored_capture_count = len(
        CRUDMinutesIndexCapture(session).get_by_capture_urls(
            [planned_capture.capture_url for planned_capture in plan.captures]
        )
    )
    if stored_capture_count != len(plan.captures):
        raise HansardWriteCheckError(
            f"{stored_capture_count} captures are stored, the plan has {len(plan.captures)}"
        )
    session.expire_all()
    sitting_date_to_stored_minutes = {
        stored_minutes.sitting_date: stored_minutes
        for stored_minutes in CRUDMinutes(session).get_by_sitting_dates(
            [planned_row.sitting_date for planned_row in plan.rows]
        )
    }
    for planned_row in plan.rows:
        stored_minutes = sitting_date_to_stored_minutes.get(planned_row.sitting_date)
        if stored_minutes is None:
            raise HansardWriteCheckError(
                f"No minutes row is stored for {planned_row.sitting_date}"
            )
        if (
            stored_minutes.status != planned_row.status
            or stored_minutes.index_source != planned_row.index_source
            or stored_minutes.file_url != planned_row.file_url
        ):
            raise HansardWriteCheckError(
                f"The stored minutes row of {planned_row.sitting_date} differs from the plan"
            )


def apply_minutes_index(
    captures_directory: Path, plan_path: Path, is_commit: bool
) -> None:
    if not is_commit:
        with Session(engine) as session:
            plan = get_minutes_index_plan(session, captures_directory)
        _log_plan(plan)
        plan_path.write_text(plan.model_dump_json(indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = MinutesIndexPlan.model_validate_json(plan_path.read_text())
    with Session(engine) as session:
        plan = get_minutes_index_plan(session, captures_directory)
        if plan != reviewed_plan:
            raise HansardWriteCheckError("The plan differs from the reviewed plan")
        _log_plan(plan)
        write_minutes_index_plan(session, plan, captures_directory)
        _validate_can_commit_minutes_index(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session, [MinutesIndexCapture.__tablename__, Minutes.__tablename__]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the Votes and Proceedings index captures of a directory and the minutes rows read from them, checked against a reviewed plan"
    )
    parser.add_argument(
        "--captures-directory",
        type=Path,
        required=True,
        help="captures.json and the HTML file of each capture",
    )
    parser.add_argument(
        "--plan-file",
        type=Path,
        required=True,
        help="the plan file: written by a dry run, read by --commit",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="check the plan is unchanged, then store the captures and minutes rows it lists",
    )
    arguments = parser.parse_args()
    apply_minutes_index(
        arguments.captures_directory, arguments.plan_file, arguments.commit
    )
