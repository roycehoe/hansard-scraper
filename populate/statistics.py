import csv

from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.parsing_statistics import CRUDParsingStatistics
from database.handsard_website_response import HandsardWebsiteResponse
from database.parsing_statistics import ParsingStatistics
from logs import logger
from services.report import build_report
from services.speech import get_speeches, get_start_of_speech_line


def _get_statistics(response: HandsardWebsiteResponse) -> ParsingStatistics:
    report = build_report(response)
    has_markdown = report.markdown_content is not None
    has_start_line = False
    can_get_speeches = False

    if has_markdown:
        start_of_speech_line = get_start_of_speech_line(
            report.markdown_content, report.title, report.subtitle, report.original_title,
            report.report_type,
        )
        has_start_line = start_of_speech_line is not None
        if has_start_line:
            get_speeches(report.markdown_content, start_of_speech_line)
            can_get_speeches = True

    return ParsingStatistics(
        **report.model_dump(),
        has_markdown=has_markdown,
        has_start_line=has_start_line,
        can_get_speeches=can_get_speeches,
    )


def populate_statistics(session: Session):
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    crud = CRUDParsingStatistics(session)
    for i, response in enumerate(responses, start=1):
        logger.info(f"{i}/{len(responses)}")
        crud.create(_get_statistics(response))


def export_statistics_csv(session: Session, path: str = "statistics.csv"):
    all_statistics = CRUDParsingStatistics(session).get_all()
    if not all_statistics:
        return
    fieldnames = list(all_statistics[0].model_dump().keys())
    with open(path, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for item in all_statistics:
            writer.writerow(item.model_dump())
