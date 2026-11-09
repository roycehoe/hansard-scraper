import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from database.init import engine
from database.report_link import ReportLink
from logs import logger
from populate.report_links import get_report_link_plan, write_report_link_plan
from populate.written_tables import vacuum_analyze_written_tables
from services.report_link import ReportLinkPlan
from settings import settings
from utils.write_target import validate_can_write


def _log_plan(plan: ReportLinkPlan) -> None:
    for (link_type, rule), count in sorted(
        Counter(
            (planned_link.link_type, planned_link.rule)
            for planned_link in plan.planned_links
        ).items()
    ):
        logger.info(f"{link_type} {rule}: {count:,} links")
    for reason, count in sorted(
        Counter(
            unplaced_citation.reason for unplaced_citation in plan.unplaced_citations
        ).items()
    ):
        logger.info(f"Unplaced {reason}: {count:,}")
    logger.info(
        f"Plan: {len(plan.planned_links):,} links, {len(plan.unplaced_citations):,} unplaced citations"
    )


def apply_report_links(is_commit: bool, unplaced_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_report_link_plan(session)
        _log_plan(plan)
        if unplaced_path is not None:
            unplaced_path.write_text(
                json.dumps(
                    [
                        asdict(unplaced_citation)
                        for unplaced_citation in plan.unplaced_citations
                    ],
                    indent=2,
                    default=str,
                )
            )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_report_link_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [ReportLink.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the links between reports that the record prints, and the links of a debate resumed on a later day"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored counts by link type and rule against the plan; without it the script only reports the plan",
    )
    parser.add_argument(
        "--unplaced-file",
        type=Path,
        help="write every citation no rule placed as JSON to this path",
    )
    arguments = parser.parse_args()
    apply_report_links(arguments.commit, arguments.unplaced_file)
