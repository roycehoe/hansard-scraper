import csv

from sqlmodel import Session, select

from database.init import create_db_and_tables, get_session
from database.report import HandsardWebsiteResponse, ParsingStatistics, Report, Speech
from gateway.handsard_search import get_all_handsard_search_results
from schemas import HandsardSearchResult
from services.handsard_website import get_handsard_website_result_in
from services.report import get_db_report_in
from services.speech import get_speeches, get_start_of_speech_line


def fetch_handsard_responses(session: Session):
    all_search_results = [
        HandsardSearchResult(**r) for r in get_all_handsard_search_results()
    ]
    for i, result in enumerate(all_search_results, start=1):
        print(f"{i}/{len(all_search_results)}")
        session.add(get_handsard_website_result_in(result))
    session.commit()


def parse_reports(session: Session):
    responses = list(session.exec(select(HandsardWebsiteResponse)).all())
    for response in responses:
        session.add(get_db_report_in(response))
    session.commit()


def _get_statistics(response: HandsardWebsiteResponse) -> ParsingStatistics:
    report = get_db_report_in(response)

    if report.markdown_content is None:
        return ParsingStatistics(
            **report.model_dump(),
            has_markdown=False,
            has_start_line=False,
            can_get_speeches=False,
        )

    start_of_speech_line = get_start_of_speech_line(
        report.markdown_content, report.title, report.subtitle, report.original_title,
        report.report_type,
    )
    if start_of_speech_line is None:
        return ParsingStatistics(
            **report.model_dump(),
            has_markdown=True,
            has_start_line=False,
            can_get_speeches=False,
        )

    try:
        get_speeches(report.markdown_content, start_of_speech_line)
    except Exception:
        return ParsingStatistics(
            **report.model_dump(),
            has_markdown=True,
            has_start_line=True,
            can_get_speeches=False,
        )

    return ParsingStatistics(
        **report.model_dump(),
        has_markdown=True,
        has_start_line=True,
        can_get_speeches=True,
    )


def compute_statistics(session: Session):
    responses = list(session.exec(select(HandsardWebsiteResponse)).all())
    all_statistics = []
    for i, response in enumerate(responses, start=1):
        print(f"{i}/{len(responses)}")
        all_statistics.append(_get_statistics(response))
    session.bulk_insert_mappings(ParsingStatistics, all_statistics)
    session.commit()

    fieldnames = list(all_statistics[0].model_dump().keys())
    with open("statistics.csv", "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for item in all_statistics:
            writer.writerow(item.model_dump())


def _chunks(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def parse_speeches(session: Session):
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


if __name__ == "__main__":
    create_db_and_tables()
    session = next(get_session())
    fetch_handsard_responses(session)
    parse_reports(session)
    compute_statistics(session)
    parse_speeches(session)
