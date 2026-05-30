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
    for i, result in enumerate(all_search_results):
        print(f"reports in: {i}/{len(all_search_results)}")
        session.add(get_handsard_website_result_in(result))
    session.commit()


def parse_reports(session: Session):
    responses = list(session.exec(select(HandsardWebsiteResponse)).all())
    for report in [get_db_report_in(r) for r in responses]:
        session.add(report)
    session.commit()


def _get_statistics(response: HandsardWebsiteResponse) -> ParsingStatistics:
    data = get_db_report_in(response)
    statistics = ParsingStatistics(**data.model_dump())

    if data.markdown_content is None:
        statistics.has_markdown = False
        statistics.has_start_line = False
        statistics.can_get_speeches = False
        return statistics

    start_of_speech_line = get_start_of_speech_line(
        data.markdown_content, data.title, data.subtitle, data.original_title
    )
    if start_of_speech_line is None:
        statistics.has_markdown = True
        statistics.has_start_line = False
        statistics.can_get_speeches = False
        return statistics

    try:
        get_speeches(data.markdown_content, start_of_speech_line)
    except Exception:
        statistics.has_markdown = True
        statistics.has_start_line = True
        statistics.can_get_speeches = False
        return statistics

    statistics.has_markdown = True
    statistics.has_start_line = True
    statistics.can_get_speeches = True
    return statistics


def compute_statistics(session: Session):
    responses = list(session.exec(select(HandsardWebsiteResponse)).all())
    all_statistics = []
    for i, response in enumerate(responses):
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


def _chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


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
