from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.report import Speech
from services.speech import get_speeches, get_start_of_speech_line


def populate_speeches(session: Session):
    db_reports = CRUDReport(session).get_all()
    all_speeches: list[Speech] = []
    for i, db_report in enumerate(db_reports, start=1):
        print(f"{i}/{len(db_reports)}")
        if db_report.markdown_content is None:
            continue
        start_of_speech_line = get_start_of_speech_line(
            db_report.markdown_content,
            db_report.title,
            db_report.subtitle,
            db_report.original_title,
            db_report.report_type,
        )
        if start_of_speech_line is None:
            continue
        for ordinal, speech in enumerate(
            get_speeches(db_report.markdown_content, start_of_speech_line)
        ):
            all_speeches.append(
                Speech(
                    ordinal=ordinal + 1,
                    speaker=speech.speaker,
                    transcript=speech.transcript,
                    report_id=db_report.id,
                )
            )
    CRUDSpeech(session).create_many(all_speeches)
