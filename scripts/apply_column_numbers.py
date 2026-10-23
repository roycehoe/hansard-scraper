import argparse

from sqlmodel import Session

import database.speaker  # noqa: F401 registers Speaker so the speech.speaker_id foreign key resolves
from crud.report import CRUDReport
from database.init import engine
from database.report import Report
from database.speech import Speech
from logs import logger
from populate.column_numbers import (
    ColumnNumberCounts,
    ColumnNumberPlan,
    get_column_number_plan,
    write_column_number_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.write_target import validate_can_write


def _log_counts(label: str, counts: ColumnNumberCounts) -> None:
    logger.info(
        f"{label}: {counts.reports:,} reports, {counts.reports_with_markers:,} with column markers, {counts.reports_with_range:,} with a column range;"
        f" {counts.rows:,} rows, {counts.rows_with_column:,} with a start column;"
        f" no start column: {', '.join(f'{reason} {count:,}' for reason, count in sorted(counts.missing_column_reason_counts.items())) or 'none'};"
        f" notes: {', '.join(f'{column_note} {count:,}' for column_note, count in sorted(counts.column_note_counts.items())) or 'none'}"
    )


def _log_plan(plan: ColumnNumberPlan) -> None:
    total_counts = ColumnNumberCounts()
    for parliament_number, counts in sorted(plan.parliament_to_counts.items()):
        _log_counts(f"Parliament {parliament_number}", counts)
        total_counts.reports += counts.reports
        total_counts.reports_with_markers += counts.reports_with_markers
        total_counts.reports_with_range += counts.reports_with_range
        total_counts.rows += counts.rows
        total_counts.rows_with_column += counts.rows_with_column
        total_counts.missing_column_reason_counts.update(counts.missing_column_reason_counts)
        total_counts.column_note_counts.update(counts.column_note_counts)
    _log_counts("All", total_counts)
    logger.info(
        f"Plan: {len(plan.report_column_ranges):,} report column ranges, {len(plan.speech_id_to_column_start):,} speech start columns"
        f" and {len(plan.speech_column_notes):,} speech column notes differ from the stored rows"
    )


def apply_column_numbers(report_ids: list[int], is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_column_number_plan(session, report_ids or [report_header_row.id for report_header_row in CRUDReport(session).get_header_rows()])
        _log_plan(plan)
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_column_number_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(session, [Report.__tablename__, Speech.__tablename__])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set each report's column range and each speech row's start column and column note from the column markers in the raw HTML")
    parser.add_argument("--report-id", type=int, nargs="+", action="extend", default=[], help="only these reports; without it every report")
    parser.add_argument("--commit", action="store_true", help="write, and check the stored counts by Parliament against the plan; without it the script only reports the plan")
    arguments = parser.parse_args()
    apply_column_numbers(arguments.report_id, arguments.commit)
