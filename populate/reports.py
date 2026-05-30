from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.report import CRUDReport
from logs import logger
from services.report import build_report


def populate_reports(session: Session):
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    crud = CRUDReport(session)
    for i, response in enumerate(responses, start=1):
        logger.info(f"{i}/{len(responses)}")
        crud.create(build_report(response))
