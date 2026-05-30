from sqlmodel import Session, select

from database.handsard_website_response import HandsardWebsiteResponse


class CRUDHandsardWebsiteResponse:
    def __init__(self, session: Session):
        self.session = session

    def create(self, response: HandsardWebsiteResponse) -> None:
        self.session.add(response)
        self.session.commit()

    def get_all(self) -> list[HandsardWebsiteResponse]:
        return list(self.session.exec(select(HandsardWebsiteResponse)).all())

    def get_all_sitting_dates(self) -> set[str]:
        return {r.sitting_date for r in self.session.exec(select(HandsardWebsiteResponse)).all()}
