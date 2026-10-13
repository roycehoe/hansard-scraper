from sqlmodel import Session

from crud.hansard_website_response import CRUDHansardWebsiteResponse
from crud.report import CRUDReport
from logs import logger
from services.report import build_report

_BATCH_SIZE = 500


def populate_reports(session: Session):
    responses = CRUDHansardWebsiteResponse(session).get_all()
    crud = CRUDReport(session)
    existing_ids = crud.get_all_report_ids()
    # The search can return one hit twice (plans/duplicate-reports.md); build one report per report_id.
    first_by_report_id = {}
    for response in responses:
        first_by_report_id.setdefault(response.report_id, response)
    to_process = [r for r in first_by_report_id.values() if r.report_id not in existing_ids]
    logger.info(f"Building {len(to_process)}/{len(responses)} reports ({len(existing_ids)} already in DB)")

    batch = []
    for i, response in enumerate(to_process, start=1):
        logger.info(f"{i}/{len(to_process)}")
        batch.append(build_report(response))
        if len(batch) >= _BATCH_SIZE:
            crud.create_many(batch)
            batch.clear()
    if batch:
        crud.create_many(batch)
