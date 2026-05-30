from sqlmodel import Session

from crud.handsard_website_response import CRUDHandsardWebsiteResponse
from crud.report import CRUDReport
from services.report import build_report


def populate_reports(session: Session):
    responses = CRUDHandsardWebsiteResponse(session).get_all()
    crud = CRUDReport(session)
    for i, response in enumerate(responses, start=1):
        print(f"{i}/{len(responses)}")
        crud.create(build_report(response))
