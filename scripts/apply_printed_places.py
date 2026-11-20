import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path

from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.report import CRUDReport
from database.init import engine
from database.report import Report
from exceptions import HansardWriteCheckError
from logs import logger
from populate.printed_places import get_printed_place_plan, write_printed_place_plan
from populate.written_tables import vacuum_analyze_written_tables
from schemas.printed_place_plan import PrintedPlacePlan
from settings import settings
from utils.sitting_dates import parse_sitting_date
from utils.write_target import validate_can_write


def _log_plan(plan: PrintedPlacePlan) -> None:
    report_version_to_rule_counts: dict[str, Counter[str]] = {}
    for rule_count in plan.rule_counts:
        logger.info(
            f"{rule_count.report_version} {rule_count.report_type} {rule_count.printed_place_rule}: {rule_count.report_count:,} reports"
        )
        report_version_to_rule_counts.setdefault(rule_count.report_version, Counter())[
            rule_count.printed_place_rule
        ] += rule_count.report_count
    for report_version, rule_counts in sorted(report_version_to_rule_counts.items()):
        logger.info(
            f"{report_version}: {sum(rule_counts.values()):,} reports; {', '.join(f'{rule} {count:,}' for rule, count in sorted(rule_counts.items()))}"
        )
    for agreement in plan.speech_number_agreements:
        if agreement.pair_count == 0:
            logger.info(f"{agreement.report_version}: no report pairs to compare")
            continue
        logger.info(
            f"{agreement.report_version}: speech_number order agrees with the printed place in {agreement.agreeing_pair_count / agreement.pair_count:.1%} of {agreement.pair_count:,} report pairs"
        )
    logger.info(
        f"Plan: {len(plan.printed_places):,} reports in {len({planned.sitting_date for planned in plan.printed_places}):,} of {len(plan.sitting_dates):,} sittings differ from the stored rows"
    )


def apply_printed_places(
    sitting_dates: list[datetime], plan_path: Path, is_commit: bool
) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_printed_place_plan(
            session, sitting_dates or CRUDReport(session).get_distinct_sitting_dates()
        )
        if is_commit:
            reviewed_plan = PrintedPlacePlan.model_validate_json(plan_path.read_text())
            if plan != reviewed_plan:
                raise HansardWriteCheckError("The plan differs from the reviewed plan")
        _log_plan(plan)
        if not is_commit:
            plan_path.write_text(plan.model_dump_json(indent=1))
            logger.info("Dry run: nothing written")
            return

        write_printed_place_plan(session, plan)
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [Report.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Set each report's printed place and rule from Parliament's own copy of its sitting, checked against a reviewed plan"
    )
    parser.add_argument(
        "--sitting-date",
        type=parse_sitting_date,
        nargs="+",
        action="extend",
        default=[],
        help="only these sitting dates, as d-m-yyyy; without it every sitting date that holds a report",
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
        help="check the plan is unchanged, then write it 50 sittings per commit, refusing a batch where two placed reports of one sitting share a place",
    )
    arguments = parser.parse_args()
    apply_printed_places(arguments.sitting_date, arguments.plan_file, arguments.commit)
