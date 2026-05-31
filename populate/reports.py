from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.report import CRUDReport
from logs import logger
from services.report import build_report

_BATCH_SIZE = 500


def populate_reports(session: Session):
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    crud = CRUDReport(session)
    existing_ids = crud.get_all_report_ids()
    to_process = [r for r in responses if r.report_id not in existing_ids]
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
