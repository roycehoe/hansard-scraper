from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.report import CRUDReport
from services.report import get_db_report_in


def populate_reports(session: Session):
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    reports = [get_db_report_in(response) for response in responses]
    CRUDReport(session).create_many(reports)
