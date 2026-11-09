import argparse

from sqlmodel import Session

from crud.report import CRUDReport
from database.init import engine
from database.report_put_to import ReportPutTo
from logs import logger
from populate.report_put_to import (
    REPORT_PUT_TO_REPORT_TYPES,
    ReportPutToPlan,
    get_report_put_to_plan,
    write_report_put_to_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.row_counts import format_row_counts
from utils.write_target import validate_can_write


def _log_plan(plan: ReportPutToPlan) -> None:
    logger.info(
        f"Plan: {len(plan.report_put_tos):,} report put-tos for {len(plan.sprs_report_ids):,} reports;"
        f" by decade: {format_row_counts(plan.decade_to_row_count)};"
        f" by source: {format_row_counts(plan.source_to_row_count)};"
        f" {plan.reports_without_phrase:,} reports with no phrase"
    )


def apply_report_put_to(report_ids: list[int], is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_report_put_to_plan(
            session,
            report_ids
            or CRUDReport(session).get_ids_by_report_types(REPORT_PUT_TO_REPORT_TYPES),
        )
        _log_plan(plan)
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_report_put_to_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [ReportPutTo.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the office each parliamentary question was put to, read from the question's speech rows"
    )
    parser.add_argument(
        "--report-id",
        type=int,
        nargs="+",
        action="extend",
        default=[],
        help="only these reports; without it every parliamentary question report",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write, and check the stored counts by decade and source against the plan; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_report_put_to(arguments.report_id, arguments.commit)
