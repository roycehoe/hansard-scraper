from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.speech import Speech
from logs import logger
from services.speech import get_speeches, get_start_of_speech_line

_BATCH_SIZE = 1000


def populate_speeches(session: Session):
    db_reports = CRUDReport(session).get_all()
    crud = CRUDSpeech(session)
    existing_report_ids = crud.get_report_ids_with_speeches()
    to_process = [r for r in db_reports if r.id not in existing_report_ids]
    logger.info(f"Parsing speeches for {len(to_process)}/{len(db_reports)} reports ({len(existing_report_ids)} already done)")

    batch = []
    for report_index, db_report in enumerate(to_process, start=1):
        logger.info(f"{report_index}/{len(to_process)}")
        if db_report.markdown_content is None:
            logger.debug(f"Skipping report {db_report.id}: no markdown content")
            continue
        start_of_speech_line = get_start_of_speech_line(
            db_report.markdown_content,
            db_report.title,
            db_report.subtitle,
            db_report.original_title,
            db_report.report_type,
        )
        if start_of_speech_line is None:
            logger.debug(f"Skipping report {db_report.id}: could not find start of speech line")
            continue
        for ordinal, speech in enumerate(
            get_speeches(db_report.markdown_content, start_of_speech_line, db_report.report_type)
        ):
            batch.append(Speech(
                ordinal=ordinal + 1,
                speaker=speech.speaker,
                transcript=speech.transcript,
                report_id=db_report.id,
            ))
        if len(batch) >= _BATCH_SIZE:
            crud.create_many(batch)
            batch.clear()

    if batch:
        crud.create_many(batch)
