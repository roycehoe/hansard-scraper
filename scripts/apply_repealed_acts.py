import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.repealed_act_entry import CRUDRepealedActEntry
from crud.repealed_acts_capture import CRUDRepealedActsCapture
from database.init import engine
from database.repealed_acts import RepealedActEntry, RepealedActsCapture
from exceptions import HansardWriteCheckError
from logs import logger
from populate.repealed_acts import (
    get_repealed_acts_plan,
    write_repealed_acts_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from schemas.repealed_acts_plan import RepealedActsPlan
from settings import settings
from utils.write_target import validate_can_write

_YEARS_PER_DECADE = 10


def _get_decade_label(enactment_year: int) -> str:
    return f"{enactment_year // _YEARS_PER_DECADE * _YEARS_PER_DECADE}s"


def _log_plan(session: Session, plan: RepealedActsPlan) -> None:
    logger.info(f"Captures: {len(plan.captures):,}")
    for planned_capture in plan.captures:
        logger.info(
            f"Capture {planned_capture.file_name}: {planned_capture.row_count:,} rows"
        )
    logger.info(
        f"Entries: {len(plan.entries):,} distinct, {plan.duplicate_count:,} duplicates dropped"
    )
    decade_to_count = Counter(
        _get_decade_label(planned_entry.enactment_year)
        for planned_entry in plan.entries
        if planned_entry.enactment_year is not None
    )
    decade_texts = [
        f"{decade} {count:,}" for decade, count in sorted(decade_to_count.items())
    ]
    no_year_count = sum(
        planned_entry.enactment_year is None for planned_entry in plan.entries
    )
    if no_year_count > 0:
        decade_texts.append(f"no year {no_year_count:,}")
    logger.info(f"Entries by decade of enactment year: {', '.join(decade_texts)}")
    stored_capture_urls = {
        capture_row.capture_url
        for capture_row in CRUDRepealedActsCapture(session).get_rows()
    }
    stored_sso_codes = {
        entry_row.sso_code for entry_row in CRUDRepealedActEntry(session).get_rows()
    }
    logger.info(
        f"Already stored: {sum(planned_capture.capture_url in stored_capture_urls for planned_capture in plan.captures):,} captures, {sum(planned_entry.sso_code in stored_sso_codes for planned_entry in plan.entries):,} entries"
    )


def _validate_can_commit_repealed_acts(
    session: Session, plan: RepealedActsPlan
) -> None:
    stored_and_planned_counts = {
        "captures": (
            CRUDRepealedActsCapture(session).get_count(),
            len(plan.captures),
        ),
        "entries": (CRUDRepealedActEntry(session).get_count(), len(plan.entries)),
    }
    for label, (stored_count, planned_count) in stored_and_planned_counts.items():
        if stored_count != planned_count:
            raise HansardWriteCheckError(
                f"{stored_count} {label} are stored, the plan has {planned_count}"
            )


def apply_repealed_acts(
    captures_directory: Path, plan_path: Path, is_commit: bool
) -> None:
    if not is_commit:
        plan = get_repealed_acts_plan(captures_directory)
        with Session(engine) as session:
            _log_plan(session, plan)
        plan_path.write_text(plan.model_dump_json(indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = RepealedActsPlan.model_validate_json(plan_path.read_text())
    plan = get_repealed_acts_plan(captures_directory)
    if plan != reviewed_plan:
        raise HansardWriteCheckError("The plan differs from the reviewed plan")
    with Session(engine) as session:
        _log_plan(session, plan)
        write_repealed_acts_plan(session, plan, captures_directory)
        _validate_can_commit_repealed_acts(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session,
            [RepealedActsCapture.__tablename__, RepealedActEntry.__tablename__],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the Internet Archive captures of the SSO repealed Acts listing and the entries parsed from them, checked against a reviewed plan"
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
        help="check the plan is unchanged, then store the captures and entries it lists",
    )
    arguments = parser.parse_args()
    apply_repealed_acts(
        arguments.captures_directory, arguments.plan_file, arguments.commit
    )
