import csv
from sqlalchemy import insert
from sqlmodel import Session, select

from database.init import create_db_and_tables, get_session
from database.report import HandsardWebsiteResponse, ParsingStatistics, Report
from gateway.handsard_search import get_all_handsard_search_results
from schemas import HandsardSearchResult
from services.handsard_website import get_handsard_website_result_in
from services.report import get_db_report_in
from services.speech import get_speeches, get_start_of_speech_line

# create_db_and_tables()

# all_handsard_search_results = [
#     HandsardSearchResult(**result) for result in get_all_handsard_search_results()
# ]
# handsard_website_reports_in = []

# for i, result in enumerate(all_handsard_search_results):
#     print(f"reports in: {i}/{len(all_handsard_search_results)}")
#     handsard_website_reports_in.append(get_handsard_website_result_in(result))

# session = next(get_session())
# for handsard_report_in in handsard_website_reports_in:
#     session.add(handsard_report_in)
# session.commit()

# session = next(get_session())
# reports = session.exec(
#     select(HandsardWebsiteResponse).where(HandsardWebsiteResponse.id == 20015)
# ).first()
# print(reports.title)


def get_handsard_website_data(session: Session, parliament_number: str):
    return list(
        session.exec(
            select(HandsardWebsiteResponse).where(
                HandsardWebsiteResponse.parliament_number == parliament_number
            )
        ).all()
    )


def write_report_data_to_db(session: Session, reports: list[HandsardWebsiteResponse]):
    db_reports_in = [get_db_report_in(report) for report in reports]
    for report in db_reports_in:
        session.add(report)
    session.commit()


def get_report_data(session: Session, parliament_number: str):
    return session.exec(
        select(Report).where(Report.parliament_number == parliament_number)
    ).all()


create_db_and_tables()
session = next(get_session())
# data = get_handsard_website_data(session, "2")
# write_report_data_to_db(session, data)

# report_data = get_report_data(session, "2")
# speeches = []
# for i in report_data:
#     if i.markdown_content is None:
#         print(i.id, "missing markdown content")
#         continue
#     start_of_speech_line = get_start_of_speech_line(
#         i.markdown_content, i.title, i.subtitle
#     )
#     if start_of_speech_line is None:
#         print(i.id, "missing start of speech line")
#         continue
#     speeches.append(i.id)

# print(speeches)


def get_statistics(response: HandsardWebsiteResponse) -> ParsingStatistics:
    data = get_db_report_in(response)
    statistics = ParsingStatistics(**data.model_dump())

    if data.markdown_content is None:
        statistics.has_markdown = False
        statistics.can_get_speeches = False
        statistics.has_start_line = False
        return statistics

    start_of_speech_line = get_start_of_speech_line(
        data.markdown_content, data.title, data.subtitle
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


def write_statistics_to_db(session: Session):
    all_statistics: list[ParsingStatistics] = []
    handsard_website_responses = list(
        session.exec(select(HandsardWebsiteResponse)).all()
    )

    for i, response in enumerate(handsard_website_responses):
        print(f"{i}/{len(handsard_website_responses)}")
        statistics = get_statistics(response)
        all_statistics.append(statistics)

    session.bulk_insert_mappings(
        ParsingStatistics,
        all_statistics,
    )
    session.commit()


handsard_website_responses = list(session.exec(select(HandsardWebsiteResponse)).all())
all_statistics = [get_statistics(i) for i in handsard_website_responses]
session.bulk_insert_mappings(
    ParsingStatistics,
    all_statistics,
)
session.commit()
# all_statistics = list(session.exec(select(ParsingStatistics)).all())


# Get field names from the first model instance for CSV header
fieldnames = list(all_statistics[0].model_dump().keys())

with open("statistics.csv", "w", newline="") as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for item in all_statistics:
        writer.writerow(item.model_dump())
