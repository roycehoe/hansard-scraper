import argparse

from sqlmodel import Session

from crud.report import CRUDReport
from database.init import engine
from database.report_participant import ReportParticipant
from database.report_question_state import ReportQuestionState
from logs import logger
from populate.report_participants import (
    REPORT_PARTICIPANT_REPORT_TYPES,
    ReportParticipantCounts,
    ReportParticipantPlan,
    get_report_participant_plan,
    write_report_participant_plan,
)
from populate.written_tables import vacuum_analyze_written_tables
from settings import settings
from utils.row_counts import format_row_counts
from utils.write_target import validate_can_write


def _log_counts(label: str, counts: ReportParticipantCounts) -> None:
    logger.info(
        f"{label}: {counts.reports:,} reports;"
        f" {sum(counts.role_to_row_count.values()):,} rows: {format_row_counts(counts.role_to_row_count)};"
        f" role source: {format_row_counts(counts.role_source_to_row_count)};"
        f" office source: {format_row_counts(counts.office_source_to_row_count)};"
        f" {counts.rows_without_speaker_id:,} with no speaker_id;"
        f" states: {format_row_counts(counts.state_to_row_count)}"
    )


def _log_plan(plan: ReportParticipantPlan) -> None:
    total_counts = ReportParticipantCounts()
    for group, counts in sorted(plan.group_to_counts.items()):
        _log_counts(group, counts)
        total_counts.reports += counts.reports
        total_counts.role_to_row_count.update(counts.role_to_row_count)
        total_counts.role_source_to_row_count.update(counts.role_source_to_row_count)
        total_counts.office_source_to_row_count.update(
            counts.office_source_to_row_count
        )
        total_counts.state_to_row_count.update(counts.state_to_row_count)
        total_counts.rows_without_speaker_id += counts.rows_without_speaker_id
    _log_counts("All", total_counts)
    logger.info(
        f"Plan: {len(plan.report_participants):,} report participants and {len(plan.report_question_states):,} report question states for {len(plan.report_ids):,} reports"
    )


def apply_report_participants(report_ids: list[int], is_commit: bool) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    with Session(engine) as session:
        plan = get_report_participant_plan(
            session,
            report_ids
            or CRUDReport(session).get_ids_by_report_types(
                REPORT_PARTICIPANT_REPORT_TYPES
            ),
        )
        _log_plan(plan)
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        write_report_participant_plan(session, plan)
        session.commit()
        logger.info("Committed")
        vacuum_analyze_written_tables(
            session,
            [ReportParticipant.__tablename__, ReportQuestionState.__tablename__],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Store the participants of each parliamentary question report, found from its speech rows"
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
        help="write, and check the stored counts by Parliament group, role, role source and office source against the plan, and the askers against report_asker; without it the script only reports the plan",
    )
    arguments = parser.parse_args()
    apply_report_participants(arguments.report_id, arguments.commit)
