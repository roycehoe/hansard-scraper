from sqlmodel import Session, select

from database.report import HandsardWebsiteResponse
from services.report import get_db_report_in


def populate_reports(session: Session):
    responses = list(session.exec(select(HandsardWebsiteResponse)).all())
    for response in responses:
        session.add(get_db_report_in(response))
    session.commit()
