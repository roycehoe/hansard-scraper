from sqlmodel import Session, select

from database.handsard_sitting_date_response import HandsardSittingDateResponse


class CRUDHandsardSittingDateResponse:
    def __init__(self, session: Session):
        self.session = session

    def create(self, response: HandsardSittingDateResponse) -> None:
        self.session.add(response)
        self.session.commit()

    def get_all(self) -> list[HandsardSittingDateResponse]:
        return list(self.session.exec(select(HandsardSittingDateResponse)).all())

    def get_all_sitting_dates(self) -> set[str]:
        return {
            r.sitting_date
            for r in self.session.exec(select(HandsardSittingDateResponse)).all()
        }
