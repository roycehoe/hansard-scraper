from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from crud.report import CRUDReport
from logs import logger
from services.report import build_report

_BATCH_SIZE = 500


def populate_reports(session: Session) -> None:
    hansard_website_responses = CRUDHansardWebsiteResponse(session).get_all()
    existing_report_ids = CRUDReport(session).get_all_report_ids()
    # NOTE: the search can return one hit twice, so keep the first hit per report_id.
    report_id_to_first_response = {}
    for hansard_website_response in hansard_website_responses:
        report_id_to_first_response.setdefault(hansard_website_response.report_id, hansard_website_response)
    responses_to_process = [hansard_website_response for hansard_website_response in report_id_to_first_response.values() if hansard_website_response.report_id not in existing_report_ids]
    logger.info(f"Building {len(responses_to_process)}/{len(hansard_website_responses)} reports ({len(existing_report_ids)} already in DB)")

    batch = []
    for i, hansard_website_response in enumerate(responses_to_process, start=1):
        logger.info(f"{i}/{len(responses_to_process)}")
        batch.append(build_report(hansard_website_response))
        if len(batch) >= _BATCH_SIZE:
            CRUDReport(session).create_many(batch)
            batch.clear()
    if batch:
        CRUDReport(session).create_many(batch)
