from sqlmodel import Session, col, select, update

from database.hansard_website_response import HansardWebsiteResponse


class CRUDHansardWebsiteResponse:
    def __init__(self, session: Session):
        self.session = session

    def create_many(self, hansard_website_responses: list[HansardWebsiteResponse]) -> None:
        self.session.add_all(hansard_website_responses)
        self.session.commit()

    def add_many(self, hansard_website_responses: list[HansardWebsiteResponse]) -> None:
        self.session.add_all(hansard_website_responses)
        self.session.flush()

    def get_all(self) -> list[HansardWebsiteResponse]:
        statement = select(HansardWebsiteResponse)
        return list(self.session.exec(statement).all())

    def get_by_report_type(self, report_type: str) -> list[HansardWebsiteResponse]:
        statement = select(HansardWebsiteResponse).where(HansardWebsiteResponse.report_type == report_type)
        return list(self.session.exec(statement).all())

    def get_by_report_ids(self, report_ids: set[str]) -> list[HansardWebsiteResponse]:
        statement = select(HansardWebsiteResponse).where(col(HansardWebsiteResponse.report_id).in_(report_ids))
        return list(self.session.exec(statement).all())

    def get_by_content_null_and_report_version(self, report_version: str) -> list[HansardWebsiteResponse]:
        statement = (
            select(HansardWebsiteResponse)
            .where(HansardWebsiteResponse.content.is_(None))
            .where(HansardWebsiteResponse.report_version == report_version)
        )
        return list(self.session.exec(statement).all())

    def set_content_by_report_id(self, report_id: str, content: str) -> None:
        statement = (
            update(HansardWebsiteResponse)
            .where(col(HansardWebsiteResponse.report_id) == report_id)
            .values(content=content)
        )

        self.session.execute(statement)

    def get_all_report_ids(self) -> set[str]:
        statement = select(HansardWebsiteResponse.report_id)
        return set(self.session.exec(statement).all())

    def get_all_sitting_dates(self) -> set[str]:
        statement = select(HansardWebsiteResponse.sitting_date).distinct()
        return set(self.session.exec(statement).all())
