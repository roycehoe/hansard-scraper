from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from logs import logger
from services.speech import ReportSkipReason, build_report_speeches
from utils.data_files import get_unattributed_speech_ranges

_BATCH_SIZE = 1_000


def populate_speeches(session: Session) -> None:
    reports = CRUDReport(session).get_all()
    existing_report_ids = CRUDSpeech(session).get_distinct_report_ids_by_report_id_not_null()
    reports_to_process = [report for report in reports if report.id not in existing_report_ids]
    report_id_to_unattributed_range = {speech_range.report_id: speech_range for speech_range in get_unattributed_speech_ranges()}
    logger.info(f"Parsing speeches for {len(reports_to_process)}/{len(reports)} reports ({len(existing_report_ids)} already done)")

    batch = []
    for report_index, report in enumerate(reports_to_process, start=1):
        logger.info(f"{report_index}/{len(reports_to_process)}")
        report_speeches = build_report_speeches(report, report_id_to_unattributed_range)
        if report_speeches.skip_reason == ReportSkipReason.NO_MARKDOWN_CONTENT:
            logger.debug(f"Skipping report {report.id}: no markdown content")
        if report_speeches.skip_reason == ReportSkipReason.NO_START_OF_SPEECH_LINE:
            logger.debug(f"Skipping report {report.id}: could not find start of speech line")
        batch.extend(report_speeches.speeches)
        if len(batch) >= _BATCH_SIZE:
            CRUDSpeech(session).create_many(batch)
            batch.clear()

    if batch:
        CRUDSpeech(session).create_many(batch)
