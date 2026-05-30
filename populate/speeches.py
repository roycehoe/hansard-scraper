from sqlmodel import Session, select

from database.report import Report, Speech
from services.speech import get_speeches, get_start_of_speech_line


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def populate_speeches(session: Session):
    db_reports = list(session.exec(select(Report)).all())
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
    for chunk in _chunks(all_speeches, 1000):
        session.bulk_insert_mappings(Speech, chunk)
    session.commit()
