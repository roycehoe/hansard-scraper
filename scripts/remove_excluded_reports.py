import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.init import engine
from database.report import Report
from exceptions import HansardWriteCheckError
from logs import logger
from schemas.excluded_report_id import ExcludedReportId
from settings import settings
from utils.write_target import validate_can_write

_EXCLUDED_REPORT_IDS_FILE = Path(__file__).parent.parent / "data" / "excluded_report_ids.json"


@dataclass(frozen=True)
class ReportRemoval:
    report_id: str
    id: int
    kept_report_id: str
    kept_id: int
    speech_count: int


def _get_validated_removal(session: Session, report: Report, kept_report: Report) -> ReportRemoval:
    if report.sitting_date != kept_report.sitting_date:
        raise HansardWriteCheckError(f"{report.report_id}: sitting date differs from {kept_report.report_id}")
    if report.content and report.content != kept_report.content:
        raise HansardWriteCheckError(f"{report.report_id}: text differs from {kept_report.report_id}")
    speech_rows = CRUDSpeech(session).get_rows_by_report_ids([report.id])
    kept_speech_rows = CRUDSpeech(session).get_rows_by_report_ids([kept_report.id])
    if speech_rows and [(row.ordinal, row.speaker, row.transcript, row.speaker_id) for row in speech_rows] != [
        (row.ordinal, row.speaker, row.transcript, row.speaker_id) for row in kept_speech_rows
    ]:
        raise HansardWriteCheckError(f"{report.report_id}: speech rows differ from {kept_report.report_id}")
    return ReportRemoval(report.report_id, report.id, kept_report.report_id, kept_report.id, len(speech_rows))


def _get_removals(session: Session, excluded_report_ids: list[ExcludedReportId]) -> list[ReportRemoval]:
    report_ids = [entry.report_id for entry in excluded_report_ids] + [entry.kept_report_id for entry in excluded_report_ids]
    report_id_to_report = {report.report_id: report for report in CRUDReport(session).get_by_report_ids(report_ids)}
    removals = []
    for entry in excluded_report_ids:
        if entry.kept_report_id not in report_id_to_report:
            raise HansardWriteCheckError(f"{entry.report_id}: the kept report {entry.kept_report_id} is not stored")
        if entry.report_id not in report_id_to_report:
            logger.info(f"{entry.report_id}: not stored, nothing to remove")
            continue
        removals.append(_get_validated_removal(session, report_id_to_report[entry.report_id], report_id_to_report[entry.kept_report_id]))
    return removals


def _remove_reports(session: Session, removals: list[ReportRemoval]) -> None:
    report_ids = [removal.id for removal in removals]
    deleted_speech_count = CRUDSpeech(session).delete_by_report_ids(report_ids)
    deleted_report_count = CRUDReport(session).delete_by_ids(report_ids)
    if deleted_speech_count != sum(removal.speech_count for removal in removals):
        raise HansardWriteCheckError(f"Deleted {deleted_speech_count} speech rows, planned {sum(removal.speech_count for removal in removals)}")
    if deleted_report_count != len(removals):
        raise HansardWriteCheckError(f"Deleted {deleted_report_count} reports, planned {len(removals)}")
    kept_ids = {removal.kept_id for removal in removals}
    if len(CRUDReport(session).get_by_ids(list(kept_ids))) != len(kept_ids):
        raise HansardWriteCheckError("A kept report is missing after the delete")


def remove_excluded_reports(is_commit: bool, plan_path: Optional[Path]) -> None:
    if is_commit:
        validate_can_write(settings.database_url)
    excluded_report_ids = [ExcludedReportId.model_validate(entry) for entry in json.loads(_EXCLUDED_REPORT_IDS_FILE.read_text())]
    with Session(engine) as session:
        removals = _get_removals(session, excluded_report_ids)
        for removal in removals:
            logger.info(f"Remove report {removal.id} ({removal.report_id}), {removal.speech_count} speech rows; keep {removal.kept_id}")
        logger.info(f"Plan: {len(removals)} reports, {sum(removal.speech_count for removal in removals)} speech rows")
        if plan_path is not None:
            plan_path.write_text(json.dumps([asdict(removal) for removal in removals], indent=2))
        if not is_commit:
            logger.info("Dry run: nothing written")
            return

        _remove_reports(session, removals)
        session.commit()
        logger.info(f"Committed: {len(removals)} reports removed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delete the stored reports listed in data/excluded_report_ids.json and their speech rows")
    parser.add_argument("--commit", action="store_true", help="write; without it the script only reports the plan")
    parser.add_argument("--plan", type=Path, help="write the plan as JSON to this path")
    arguments = parser.parse_args()
    remove_excluded_reports(arguments.commit, arguments.plan)
