import argparse
from collections import Counter
from pathlib import Path

from sqlmodel import Session

from crud.report import CRUDReport
from database.division import Division
from database.init import engine
from exceptions import HansardWriteCheckError
from logs import logger
from populate.divisions import (
    get_decade_and_source_counts,
    get_division_match,
    get_division_plan,
    write_division_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from schemas.division_plan import DivisionPlan
from settings import settings
from utils.write_target import validate_can_write


def _log_plan(session: Session, plan: DivisionPlan) -> None:
    logger.info(
        f"Plan: {len(plan.divisions):,} divisions in {len(plan.report_ids):,} reports, {len(plan.unread_rows):,} unread rows"
    )
    decade_and_source_counts = get_decade_and_source_counts(plan.divisions)
    logger.info(
        f"Divisions by decade and source: {', '.join(f'{decade} {source} {count:,}' for (decade, source), count in sorted(decade_and_source_counts.items()))}"
    )
    reason_to_count = Counter(unread_row.reason for unread_row in plan.unread_rows)
    logger.info(
        f"Unread rows by reason: {', '.join(f'{reason} {count:,}' for reason, count in sorted(reason_to_count.items())) or 'none'}"
    )
    match = get_division_match(session, plan)
    updated_count = len(match.division_updates)
    added_count = len(match.divisions_to_add)
    kept_count = len(plan.divisions) - updated_count - added_count
    logger.info(
        f"Against stored: {kept_count:,} kept, {updated_count:,} updated, {added_count:,} added, {len(match.division_ids_to_delete):,} deleted"
    )


def apply_divisions(report_ids: list[int], plan_path: Path, is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_division_plan(session, report_ids or CRUDReport(session).get_ids())
        if is_commit:
            reviewed_plan = DivisionPlan.model_validate_json(plan_path.read_text())
            if plan != reviewed_plan:
                raise HansardWriteCheckError("The plan differs from the reviewed plan")
        _log_plan(session, plan)
        if not is_commit:
            plan_path.write_text(plan.model_dump_json(indent=1))
            logger.info("Dry run: nothing written")
            return

        write_division_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [Division.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the divisions of each report, read from its speech rows, checked against a reviewed plan"
    )
    parser.add_argument(
        "--report-id",
        type=int,
        nargs="+",
        action="extend",
        default=[],
        help="only these reports; without it every report",
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
        help="check the plan is unchanged, then write it, check the stored counts by decade and source against the plan, and commit",
    )
    arguments = parser.parse_args()
    apply_divisions(arguments.report_id, arguments.plan_file, arguments.commit)
