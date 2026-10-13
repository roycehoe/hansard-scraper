from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from crud.report import CRUDReport
from logs import logger
from services.report import build_report

_BATCH_SIZE = 500


def populate_reports(session: Session) -> None:
    responses = CRUDHansardWebsiteResponse(session).get_all()
    existing_ids = CRUDReport(session).get_all_report_ids()
    # NOTE: the search can return one hit twice, so keep the first hit per report_id.
    first_by_report_id = {}
    for response in responses:
        first_by_report_id.setdefault(response.report_id, response)
    reports_to_process = [response for response in first_by_report_id.values() if response.report_id not in existing_ids]
    logger.info(f"Building {len(reports_to_process)}/{len(responses)} reports ({len(existing_ids)} already in DB)")

    batch = []
    for i, response in enumerate(reports_to_process, start=1):
        logger.info(f"{i}/{len(reports_to_process)}")
        batch.append(build_report(response))
        if len(batch) >= _BATCH_SIZE:
            CRUDReport(session).create_many(batch)
            batch.clear()
    if batch:
        CRUDReport(session).create_many(batch)
