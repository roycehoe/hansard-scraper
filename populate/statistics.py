import csv

from sqlmodel import Session

from crud.parsing_statistics import CRUDParsingStatistics
from crud.report import CRUDReport
from database.parsing_statistics import ParsingStatistics
from database.report import Report
from logs import logger
from services.speech import get_speeches, get_start_of_speech_line

_BATCH_SIZE = 500


def _get_statistics(report: Report) -> ParsingStatistics:
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
            get_speeches(report.markdown_content, start_of_speech_line, report.report_type)
            can_get_speeches = True

    return ParsingStatistics(
        **report.model_dump(exclude={"id", "speeches"}),
        has_markdown=has_markdown,
        has_start_line=has_start_line,
        can_get_speeches=can_get_speeches,
    )


def populate_statistics(session: Session):
    reports = CRUDReport(session).get_all()
    crud = CRUDParsingStatistics(session)
    existing_ids = crud.get_all_report_ids()
    to_process = [r for r in reports if r.report_id not in existing_ids]
    logger.info(f"Computing statistics for {len(to_process)}/{len(reports)} ({len(existing_ids)} already done)")

    batch = []
    for i, report in enumerate(to_process, start=1):
        logger.info(f"{i}/{len(to_process)}")
        batch.append(_get_statistics(report))
        if len(batch) >= _BATCH_SIZE:
            crud.create_many(batch)
            batch.clear()
    if batch:
        crud.create_many(batch)


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
