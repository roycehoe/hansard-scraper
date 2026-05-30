from sqlmodel import Session, select

from database.report import HandsardSittingDateResponse


class CRUDHandsardSittingDateResponse:
    def __init__(self, session: Session):
        self.session = session

    def create_many(self, results: list[HandsardSittingDateResponse]) -> None:
        for result in results:
            self.session.add(result)
        self.session.commit()

    def get_all_sitting_dates(self) -> set[str]:
        return {r.sitting_date for r in self.session.exec(select(HandsardSittingDateResponse)).all()}
