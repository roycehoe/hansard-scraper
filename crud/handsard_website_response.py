from sqlmodel import Session, col, select

from database.handsard_website_response import HandsardWebsiteResponse


class CRUDHandsardWebsiteResponse:
    def __init__(self, session: Session):
        self.session = session

    def create(self, response: HandsardWebsiteResponse) -> None:
        self.session.add(response)
        self.session.commit()

    def get_all(self) -> list[HandsardWebsiteResponse]:
        return list(self.session.exec(select(HandsardWebsiteResponse)).all())

    def get_all_by_report_type(self, report_type: str) -> list[HandsardWebsiteResponse]:
        return list(self.session.exec(
            select(HandsardWebsiteResponse).where(HandsardWebsiteResponse.report_type == report_type)
        ).all())

    def get_all_by_report_ids(self, report_ids: set[str]) -> list[HandsardWebsiteResponse]:
        return list(self.session.exec(
            select(HandsardWebsiteResponse).where(col(HandsardWebsiteResponse.report_id).in_(report_ids))
        ).all())

    def get_all_sitting_dates(self) -> set[str]:
        return set(self.session.exec(
            select(HandsardWebsiteResponse.sitting_date).distinct()
        ).all())
