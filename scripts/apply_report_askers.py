import argparse

from sqlmodel import Session

from crud.report import CRUDReport
from database.init import engine
from database.report_asker import ReportAsker
from logs import logger
from populate.report_askers import (
    REPORT_ASKER_REPORT_TYPES,
    ReportAskerCounts,
    ReportAskerPlan,
    get_report_asker_plan,
    write_report_asker_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write


def _log_counts(label: str, counts: ReportAskerCounts) -> None:
    logger.info(
        f"{label}: {counts.reports:,} reports, {counts.reports_with_resolved_asker:,} with an asker;"
        f" {sum(counts.source_to_row_count.values()):,} rows: {', '.join(f'{source} {count:,}' for source, count in sorted(counts.source_to_row_count.items())) or 'none'};"
        f" {counts.rows_without_speaker_id:,} with no speaker_id;"
        f" stood: {counts.stood_rows_with_reader:,} with a reader, {counts.stood_rows_without_reader:,} without"
    )


def _log_plan(plan: ReportAskerPlan) -> None:
    total_counts = ReportAskerCounts()
    for group, counts in sorted(plan.group_to_counts.items()):
        _log_counts(group, counts)
        total_counts.reports += counts.reports
        total_counts.reports_with_resolved_asker += counts.reports_with_resolved_asker
        total_counts.source_to_row_count.update(counts.source_to_row_count)
        total_counts.rows_without_speaker_id += counts.rows_without_speaker_id
        total_counts.stood_rows_with_reader += counts.stood_rows_with_reader
        total_counts.stood_rows_without_reader += counts.stood_rows_without_reader
    _log_counts("All", total_counts)
    logger.info(
        f"Plan: {len(plan.report_askers):,} report askers for {len(plan.report_ids):,} reports"
    )


def apply_report_askers(report_ids: list[int], is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_report_asker_plan(
            session,
            report_ids
            or [
                report_row.id
                for report_row in CRUDReport(
                    session
                ).get_asker_report_rows_by_report_types(REPORT_ASKER_REPORT_TYPES)
            ],
        )
        _log_plan(plan)
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_report_asker_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [ReportAsker.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the askers of each parliamentary question report, found from its speech rows"
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
        help="write, and check the stored counts by Parliament group and source against the plan; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_report_askers(arguments.report_id, arguments.commit)
