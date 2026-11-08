import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.acts_supplement_capture import CRUDActsSupplementCapture
from crud.acts_supplement_entry import CRUDActsSupplementEntry
from database.acts_supplement import ActsSupplementCapture, ActsSupplementEntry
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from populate.acts_supplements import (
    get_acts_supplement_plan,
    write_acts_supplement_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from schemas.acts_supplement_plan import ActsSupplementPlan
from settings import settings
from utils.write_target import validate_can_write

_YEARS_PER_DECADE = 10


def _get_decade_label(act_number: str) -> str:
    year = int(act_number.split("/")[1])
    return f"{year // _YEARS_PER_DECADE * _YEARS_PER_DECADE}s"


def _log_plan(session: Session, plan: ActsSupplementPlan) -> None:
    logger.info(f"Captures: {len(plan.captures):,}")
    for planned_capture in plan.captures:
        logger.info(
            f"Capture {planned_capture.file_name}: {planned_capture.row_count:,} rows"
        )
    logger.info(
        f"Entries: {len(plan.entries):,} distinct, {plan.duplicate_count:,} duplicates dropped"
    )
    decade_to_count = Counter(
        _get_decade_label(planned_entry.act_number) for planned_entry in plan.entries
    )
    logger.info(
        f"Entries by decade of act number: {', '.join(f'{decade} {count:,}' for decade, count in sorted(decade_to_count.items()))}"
    )
    stored_capture_urls = {
        capture_row.capture_url
        for capture_row in CRUDActsSupplementCapture(session).get_rows()
    }
    stored_act_numbers_and_links = {
        (entry_row.act_number, entry_row.link)
        for entry_row in CRUDActsSupplementEntry(session).get_rows()
    }
    logger.info(
        f"Already stored: {sum(planned_capture.capture_url in stored_capture_urls for planned_capture in plan.captures):,} captures, {sum((planned_entry.act_number, planned_entry.link) in stored_act_numbers_and_links for planned_entry in plan.entries):,} entries"
    )


def _validate_can_commit_acts_supplement(
    session: Session, plan: ActsSupplementPlan
) -> None:
    stored_and_planned_counts = {
        "captures": (
            CRUDActsSupplementCapture(session).get_count(),
            len(plan.captures),
        ),
        "entries": (CRUDActsSupplementEntry(session).get_count(), len(plan.entries)),
    }
    for label, (stored_count, planned_count) in stored_and_planned_counts.items():
        if stored_count != planned_count:
            raise HansardWriteCheckError(
                f"{stored_count} {label} are stored, the plan has {planned_count}"
            )


def apply_acts_supplement(
    captures_directory: Path, plan_path: Path, is_commit: bool
) -> None:
    if not is_commit:
        plan = get_acts_supplement_plan(captures_directory)
        with Session(engine) as session:
            _log_plan(session, plan)
        plan_path.write_text(plan.model_dump_json(indent=1))
        logger.info("Dry run: nothing written")
        return

    validate_can_write(settings.database_url)
    reviewed_plan = ActsSupplementPlan.model_validate_json(plan_path.read_text())
    plan = get_acts_supplement_plan(captures_directory)
    if plan != reviewed_plan:
        raise HansardWriteCheckError("The plan differs from the reviewed plan")
    with Session(engine) as session:
        _log_plan(session, plan)
        write_acts_supplement_plan(session, plan, captures_directory)
        _validate_can_commit_acts_supplement(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session,
            [ActsSupplementCapture.__tablename__, ActsSupplementEntry.__tablename__],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the Internet Archive captures of the SSO Acts Supplement listing and the entries parsed from them, checked against a reviewed plan"
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
    apply_acts_supplement(
        arguments.captures_directory, arguments.plan_file, arguments.commit
    )
