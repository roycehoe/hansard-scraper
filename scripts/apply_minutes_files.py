import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.minutes import CRUDMinutes
from database.init import engine
from database.minutes import Minutes
from enums import MinutesIndexSource, MinutesStatus
from exceptions import HansardWriteCheckError
from logs import logger
from populate.minutes_files import get_minutes_files_plan, write_minutes_files_plan
from populate.written_tables import vacuum_analyze_written_tables
from schemas.minutes_files_plan import MinutesFilesPlan
from settings import settings
from utils.write_target import validate_can_write


def _get_status_counts(session: Session) -> Counter[MinutesStatus]:
    session.expire_all()
    return Counter(
        stored_minutes.status
        for stored_minutes in CRUDMinutes(session).get_by_statuses(list(MinutesStatus))
    )


def _log_plan(session: Session, plan: MinutesFilesPlan) -> None:
    logger.info(
        f"Files: {len(plan.files):,} planned, {plan.already_stored_count:,} already stored, {len(plan.flagged):,} flagged"
    )
    status_to_count = Counter(planned_file.status.value for planned_file in plan.files)
    logger.info(
        f"Files by status: {', '.join(f'{status} {count:,}' for status, count in sorted(status_to_count.items())) or 'none'}"
    )
    new_count = sum(planned_file.is_new_row for planned_file in plan.files)
    moved_count = sum(
        not planned_file.is_new_row
        and planned_file.index_source == MinutesIndexSource.ARCHIVE_FILE_LISTING
        for planned_file in plan.files
    )
    logger.info(f"Rows: {new_count:,} new, {moved_count:,} moved by a listing file")
    for flagged_file in plan.flagged:
        logger.info(f"Flagged {flagged_file.file_url}: {flagged_file.reason}")
    if (
        CRUDMinutes(session).get_min_sitting_date_by_index_source(
            MinutesIndexSource.LIVE_PAGE
        )
        is None
    ):
        logger.info(
            "No LIVE_PAGE row is stored: no NOT_YET_LISTED row moves to FILE_NOT_FOUND"
        )


def _validate_can_commit_minutes_files(
    session: Session,
    plan: MinutesFilesPlan,
    status_to_count_before: Counter[MinutesStatus],
) -> None:
    session.expire_all()
    sitting_date_to_stored_minutes = {
        stored_minutes.sitting_date: stored_minutes
        for stored_minutes in CRUDMinutes(session).get_by_sitting_dates(
            [planned_file.sitting_date for planned_file in plan.files]
        )
    }
    expected_status_to_count = Counter(status_to_count_before)
    for planned_file in plan.files:
        stored_minutes = sitting_date_to_stored_minutes.get(planned_file.sitting_date)
        if stored_minutes is None:
            raise HansardWriteCheckError(
                f"No minutes row is stored for {planned_file.sitting_date}"
            )
        if (
            stored_minutes.status != planned_file.status
            or stored_minutes.sha256 != planned_file.sha256
            or stored_minutes.file_url != planned_file.file_url
        ):
            raise HansardWriteCheckError(
                f"The stored minutes row of {planned_file.sitting_date} differs from the plan"
            )
        expected_status_to_count[planned_file.status] += 1
        if planned_file.expected_status is not None:
            expected_status_to_count[planned_file.expected_status] -= 1
    status_to_count_after = _get_status_counts(session)
    for status in MinutesStatus:
        if status_to_count_after[status] != expected_status_to_count[status]:
            raise HansardWriteCheckError(
                f"{status_to_count_after[status]} {status} rows are stored, expected {expected_status_to_count[status]}"
            )


def apply_minutes_files(
    files_directory: Path, plan_path: Path, is_commit: bool
) -> None:
    if not is_commit:
        with Session(engine) as session:
            plan = get_minutes_files_plan(session, files_directory)
            _log_plan(session, plan)
        plan_path.write_text(plan.model_dump_json(indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = MinutesFilesPlan.model_validate_json(plan_path.read_text())
    with Session(engine) as session:
        plan = get_minutes_files_plan(session, files_directory)
        if plan != reviewed_plan:
            raise HansardWriteCheckError("The plan differs from the reviewed plan")
        _log_plan(session, plan)
        status_to_count_before = _get_status_counts(session)
        write_minutes_files_plan(session, plan, files_directory)
        _validate_can_commit_minutes_files(session, plan, status_to_count_before)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [Minutes.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the files fetched for the Votes and Proceedings, their text and the rows they list, checked against a reviewed plan"
    )
    parser.add_argument(
        "--files-directory",
        type=Path,
        required=True,
        help="fetches.json and the files it names",
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
        help="check the plan is unchanged, then store the files and the rows it lists",
    )
    arguments = parser.parse_args()
    apply_minutes_files(
        arguments.files_directory, arguments.plan_file, arguments.commit
    )
