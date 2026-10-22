from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from crud.report import CRUDReport
from database.hansard_website_response import HansardWebsiteResponse
from logs import logger
from utils.markdown_parser import get_cleaned_report_markdown

_BATCH_SIZE = 500


def populate_report_contents(session: Session) -> None:
    reports = CRUDReport(session).get_by_content_null()
    logger.info(f"Filling {len(reports)} reports without content")

    filled = 0
    skipped = 0
    for start in range(0, len(reports), _BATCH_SIZE):
        batch = reports[start : start + _BATCH_SIZE]
        hansard_website_responses = CRUDHansardWebsiteResponse(session).get_by_report_ids({report.report_id for report in batch})
        report_id_to_first_response: dict[str, HansardWebsiteResponse] = {}
        for hansard_website_response in hansard_website_responses:
            if hansard_website_response.content is None:
                continue
            report_id_to_first_response.setdefault(hansard_website_response.report_id, hansard_website_response)

        for report in batch:
            hansard_website_response = report_id_to_first_response.get(report.report_id)
            if hansard_website_response is None:
                logger.debug(f"Skipping report {report.report_id}: no raw text")
                skipped += 1
                continue
            report.content = hansard_website_response.content
            report.markdown_content = get_cleaned_report_markdown(hansard_website_response.content, report.report_version)
            CRUDReport(session).update(report)
            filled += 1
            logger.info(f"{filled + skipped}/{len(reports)}: {report.report_id}")
    session.commit()
    logger.info(f"Report contents: {filled} reports filled, {skipped} reports skipped")
