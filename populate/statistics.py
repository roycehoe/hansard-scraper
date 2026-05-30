import csv

from sqlmodel import Session, select

from database.report import HandsardWebsiteResponse, ParsingStatistics
from services.report import get_db_report_in
from services.speech import get_speeches, get_start_of_speech_line


def _get_statistics(response: HandsardWebsiteResponse) -> ParsingStatistics:
    report = get_db_report_in(response)
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
            try:
                get_speeches(report.markdown_content, start_of_speech_line)
                can_get_speeches = True
            except Exception:
                pass

    return ParsingStatistics(
        **report.model_dump(),
        has_markdown=has_markdown,
        has_start_line=has_start_line,
        can_get_speeches=can_get_speeches,
    )


def populate_statistics(session: Session):
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
