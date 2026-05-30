from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.report import CRUDReport
from services.report import get_db_report_in


def populate_reports(session: Session):
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    crud = CRUDReport(session)
    for i, response in enumerate(responses, start=1):
        print(f"{i}/{len(responses)}")
        crud.create(get_db_report_in(response))
