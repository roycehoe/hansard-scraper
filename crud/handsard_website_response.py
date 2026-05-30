from sqlmodel import Session, select

from database.report import HandsardWebsiteResponse


class CRUDHandsardWebsiteResponse:
    def __init__(self, session: Session):
        self.session = session

    def create_many(self, responses: list[HandsardWebsiteResponse]) -> None:
        for response in responses:
            self.session.add(response)
        self.session.commit()

    def get_all(self) -> list[HandsardWebsiteResponse]:
        return list(self.session.exec(select(HandsardWebsiteResponse)).all())

    def get_all_sitting_dates(self) -> set[str]:
        return {r.sitting_date for r in self.session.exec(select(HandsardWebsiteResponse)).all()}
