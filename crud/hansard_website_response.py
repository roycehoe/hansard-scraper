from sqlmodel import Session, col, select

from database.hansard_website_response import HansardWebsiteResponse


class CRUDHansardWebsiteResponse:
    def __init__(self, session: Session):
        self.session = session

    def create(self, response: HansardWebsiteResponse) -> None:
        self.session.add(response)
        self.session.commit()

    def create_many(self, responses: list[HansardWebsiteResponse]) -> None:
        self.session.add_all(responses)
        self.session.commit()

    def get_all(self) -> list[HansardWebsiteResponse]:
        statement = select(HansardWebsiteResponse)
        return list(self.session.exec(statement).all())

    def get_all_by_report_type(self, report_type: str) -> list[HansardWebsiteResponse]:
        statement = select(HansardWebsiteResponse).where(HansardWebsiteResponse.report_type == report_type)
        return list(self.session.exec(statement).all())

    def get_all_by_report_ids(self, report_ids: set[str]) -> list[HansardWebsiteResponse]:
        statement = select(HansardWebsiteResponse).where(col(HansardWebsiteResponse.report_id).in_(report_ids))
        return list(self.session.exec(statement).all())

    def get_all_report_ids(self) -> set[str]:
        statement = select(HansardWebsiteResponse.report_id)
        return set(self.session.exec(statement).all())

    def get_all_sitting_dates(self) -> set[str]:
        statement = select(HansardWebsiteResponse.sitting_date).distinct()
        return set(self.session.exec(statement).all())
