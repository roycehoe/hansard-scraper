from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.report import Report
from database.speech import Speech
from logs import logger
from schemas.unattributed_speech import UnattributedSpeechRange
from services.speech import (
    apply_unattributed_speech_range,
    build_speeches,
    get_speeches,
    get_start_of_speech_line,
)
from utils.data_files import get_unattributed_speech_ranges

_BATCH_SIZE = 1_000


def build_report_speeches(report: Report, report_id_to_unattributed_range: dict[int, UnattributedSpeechRange]) -> list[Speech]:
    if report.markdown_content is None:
        logger.debug(f"Skipping report {report.id}: no markdown content")
        return []
    start_of_speech_line = get_start_of_speech_line(
        report.markdown_content,
        report.title,
        report.subtitle,
        report.original_title,
        report.report_type,
        report.report_version,
    )
    if start_of_speech_line is None:
        logger.debug(f"Skipping report {report.id}: could not find start of speech line")
        return []
    speeches = get_speeches(report.markdown_content, start_of_speech_line, report.report_type, report.report_version)
    unattributed_range = report_id_to_unattributed_range.get(report.id)
    speeches_to_store = speeches if unattributed_range is None else apply_unattributed_speech_range(speeches, unattributed_range)
    return build_speeches(report, speeches_to_store)


def populate_speeches(session: Session) -> None:
    reports = CRUDReport(session).get_all()
    existing_report_ids = CRUDSpeech(session).get_distinct_report_ids_by_report_id_not_null()
    reports_to_process = [report for report in reports if report.id not in existing_report_ids]
    report_id_to_unattributed_range = {speech_range.report_id: speech_range for speech_range in get_unattributed_speech_ranges()}
    logger.info(f"Parsing speeches for {len(reports_to_process)}/{len(reports)} reports ({len(existing_report_ids)} already done)")

    batch = []
    for report_index, report in enumerate(reports_to_process, start=1):
        logger.info(f"{report_index}/{len(reports_to_process)}")
        batch.extend(build_report_speeches(report, report_id_to_unattributed_range))
        if len(batch) >= _BATCH_SIZE:
            CRUDSpeech(session).create_many(batch)
            batch.clear()

    if batch:
        CRUDSpeech(session).create_many(batch)
