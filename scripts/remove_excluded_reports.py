import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.report import CRUDReport
from crud.report_asker import CRUDReportAsker
from crud.report_link import CRUDReportLink
from crud.report_participant import CRUDReportParticipant
from crud.report_put_to import CRUDReportPutTo
from crud.report_question_state import CRUDReportQuestionState
from crud.speech import CRUDSpeech
from database.init import engine
from database.report import Report
from database.report_asker import ReportAsker
from database.report_link import ReportLink
from database.report_participant import ReportParticipant
from database.report_put_to import ReportPutTo
from database.report_question_state import ReportQuestionState
from database.speech import Speech
from exceptions import HansardWriteCheckError
from logs import logger
from populate.written_tables import vacuum_analyze_written_tables
from schemas.excluded_report_id import ExcludedReportId
from settings import settings
from utils.data_files import get_excluded_report_ids
from utils.write_target import validate_can_write


@dataclass(frozen=True)
class ReportRemoval:
    report_id: str
    id: int
    kept_report_id: str
    kept_id: int
    speech_count: int
    asker_count: int
    participant_count: int
    question_state_count: int
    put_to_count: int
    link_count: int


def _get_validated_removal(
    session: Session, report: Report, kept_report: Report
) -> ReportRemoval:
    if report.sitting_date != kept_report.sitting_date:
        raise HansardWriteCheckError(
            f"{report.report_id}: sitting date differs from {kept_report.report_id}"
        )
    if report.content and report.content != kept_report.content:
        raise HansardWriteCheckError(
            f"{report.report_id}: text differs from {kept_report.report_id}"
        )
    speech_rows = CRUDSpeech(session).get_rows_by_report_ids([report.id])
    kept_speech_rows = CRUDSpeech(session).get_rows_by_report_ids([kept_report.id])
    if speech_rows and [
        (
            speech_row.ordinal,
            speech_row.speaker,
            speech_row.transcript,
            speech_row.speaker_id,
        )
        for speech_row in speech_rows
    ] != [
        (
            speech_row.ordinal,
            speech_row.speaker,
            speech_row.transcript,
            speech_row.speaker_id,
        )
        for speech_row in kept_speech_rows
    ]:
        raise HansardWriteCheckError(
            f"{report.report_id}: speech rows differ from {kept_report.report_id}"
        )
    return ReportRemoval(
        report.report_id,
        report.id,
        kept_report.report_id,
        kept_report.id,
        len(speech_rows),
        len(CRUDReportAsker(session).get_rows_by_report_ids([report.id])),
        len(CRUDReportParticipant(session).get_rows_by_report_ids([report.id])),
        len(CRUDReportQuestionState(session).get_rows_by_report_ids([report.id])),
        len(CRUDReportPutTo(session).get_rows_by_sprs_report_ids([report.report_id])),
        len(CRUDReportLink(session).get_rows_by_source_report_ids([report.report_id]))
        + len(
            CRUDReportLink(session).get_rows_by_target_report_ids([report.report_id])
        ),
    )


def _get_removals(
    session: Session, excluded_report_ids: list[ExcludedReportId]
) -> list[ReportRemoval]:
    report_ids = [
        excluded_report_id.report_id for excluded_report_id in excluded_report_ids
    ] + [
        excluded_report_id.kept_report_id for excluded_report_id in excluded_report_ids
    ]
    report_id_to_report = {
        report.report_id: report
        for report in CRUDReport(session).get_by_report_ids(report_ids)
    }
    removals = []
    for excluded_report_id in excluded_report_ids:
        if excluded_report_id.kept_report_id not in report_id_to_report:
            raise HansardWriteCheckError(
                f"{excluded_report_id.report_id}: the kept report {excluded_report_id.kept_report_id} is not stored"
            )
        if excluded_report_id.report_id not in report_id_to_report:
            logger.info(
                f"{excluded_report_id.report_id}: not stored, nothing to remove"
            )
            continue
        removals.append(
            _get_validated_removal(
                session,
                report_id_to_report[excluded_report_id.report_id],
                report_id_to_report[excluded_report_id.kept_report_id],
            )
        )
    return removals


def _remove_reports(session: Session, removals: list[ReportRemoval]) -> None:
    report_ids = [removal.id for removal in removals]
    report_sprs_ids = [removal.report_id for removal in removals]
    planned_link_ids = {
        report_link_row.id
        for report_link_row in CRUDReportLink(session).get_rows_by_source_report_ids(
            report_sprs_ids
        )
        + CRUDReportLink(session).get_rows_by_target_report_ids(report_sprs_ids)
    }
    deleted_link_count = CRUDReportLink(session).delete_by_source_report_ids(
        report_sprs_ids
    ) + CRUDReportLink(session).delete_by_target_report_ids(report_sprs_ids)
    deleted_asker_count = CRUDReportAsker(session).delete_by_report_ids(report_ids)
    deleted_participant_count = CRUDReportParticipant(session).delete_by_report_ids(
        report_ids
    )
    deleted_question_state_count = CRUDReportQuestionState(
        session
    ).delete_by_report_ids(report_ids)
    deleted_put_to_count = CRUDReportPutTo(session).delete_by_sprs_report_ids(
        [removal.report_id for removal in removals]
    )
    deleted_speech_count = CRUDSpeech(session).delete_by_report_ids(report_ids)
    deleted_report_count = CRUDReport(session).delete_by_ids(report_ids)
    if deleted_link_count != len(planned_link_ids):
        raise HansardWriteCheckError(
            f"Deleted {deleted_link_count} report link rows, planned {len(planned_link_ids)}"
        )
    if deleted_asker_count != sum(removal.asker_count for removal in removals):
        raise HansardWriteCheckError(
            f"Deleted {deleted_asker_count} asker rows, planned {sum(removal.asker_count for removal in removals)}"
        )
    if deleted_participant_count != sum(
        removal.participant_count for removal in removals
    ):
        raise HansardWriteCheckError(
            f"Deleted {deleted_participant_count} participant rows, planned {sum(removal.participant_count for removal in removals)}"
        )
    if deleted_question_state_count != sum(
        removal.question_state_count for removal in removals
    ):
        raise HansardWriteCheckError(
            f"Deleted {deleted_question_state_count} question state rows, planned {sum(removal.question_state_count for removal in removals)}"
        )
    if deleted_put_to_count != sum(removal.put_to_count for removal in removals):
        raise HansardWriteCheckError(
            f"Deleted {deleted_put_to_count} put-to rows, planned {sum(removal.put_to_count for removal in removals)}"
        )
    if deleted_speech_count != sum(removal.speech_count for removal in removals):
        raise HansardWriteCheckError(
            f"Deleted {deleted_speech_count} speech rows, planned {sum(removal.speech_count for removal in removals)}"
        )
    if deleted_report_count != len(removals):
        raise HansardWriteCheckError(
            f"Deleted {deleted_report_count} reports, planned {len(removals)}"
        )
    kept_ids = {removal.kept_id for removal in removals}
    if len(CRUDReport(session).get_by_ids(list(kept_ids))) != len(kept_ids):
        raise HansardWriteCheckError("A kept report is missing after the delete")


def remove_excluded_reports(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    excluded_report_ids = get_excluded_report_ids()
    with Session(engine) as session:
        removals = _get_removals(session, excluded_report_ids)
        for removal in removals:
            logger.info(
                f"Remove report {removal.id} ({removal.report_id}), {removal.speech_count} speech rows, {removal.asker_count} asker rows, {removal.participant_count} participant rows, {removal.question_state_count} question state rows, {removal.put_to_count} put-to rows, {removal.link_count} link rows; keep {removal.kept_id}"
            )
        logger.info(
            f"Plan: {len(removals)} reports, {sum(removal.speech_count for removal in removals)} speech rows, {sum(removal.asker_count for removal in removals)} asker rows, {sum(removal.participant_count for removal in removals)} participant rows, {sum(removal.question_state_count for removal in removals)} question state rows, {sum(removal.put_to_count for removal in removals)} put-to rows, {sum(removal.link_count for removal in removals)} link rows"
        )
        if plan_path is not None:
            plan_path.write_text(
                json.dumps([asdict(removal) for removal in removals], indent=2)
            )
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _remove_reports(session, removals)
        session.commit()
        logger.info(f"Committed: {len(removals)} reports removed")
        vacuum_analyze_written_tables(
            session,
            [
                Speech.__tablename__,
                ReportAsker.__tablename__,
                ReportParticipant.__tablename__,
                ReportQuestionState.__tablename__,
                ReportPutTo.__tablename__,
                ReportLink.__tablename__,
                Report.__tablename__,
            ],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Delete the stored reports listed in data/excluded_report_ids.json and their speech, asker, participant, question state and report link rows"
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="write; without it the script only reports the plan",
    )
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    remove_excluded_reports(arguments.commit, arguments.plan)
