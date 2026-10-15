from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.speech import Speech
from logs import logger
from services.speech import get_speeches, get_start_of_speech_line

_BATCH_SIZE = 1_000


def populate_speeches(session: Session) -> None:
    reports = CRUDReport(session).get_all()
    existing_report_ids = CRUDSpeech(session).get_distinct_report_ids()
    reports_to_process = [report for report in reports if report.id not in existing_report_ids]
    logger.info(f"Parsing speeches for {len(reports_to_process)}/{len(reports)} reports ({len(existing_report_ids)} already done)")

    batch = []
    for report_index, report in enumerate(reports_to_process, start=1):
        logger.info(f"{report_index}/{len(reports_to_process)}")
        if report.markdown_content is None:
            logger.debug(f"Skipping report {report.id}: no markdown content")
            continue
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
            continue
        for ordinal, speech in enumerate(
            get_speeches(
                report.markdown_content, start_of_speech_line, report.report_type, report.report_version
            )
        ):
            batch.append(Speech(
                ordinal=ordinal + 1,
                speaker=speech.speaker,
                transcript=speech.transcript,
                kind=speech.kind,
                report_id=report.id,
            ))
        if len(batch) >= _BATCH_SIZE:
            CRUDSpeech(session).create_many(batch)
            batch.clear()

    if batch:
        CRUDSpeech(session).create_many(batch)
