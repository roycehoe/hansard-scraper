from sqlmodel import Session, select

from database.report import HandsardSittingDateResult


class CRUDHandsardSittingDateResult:
    def __init__(self, session: Session):
        self.session = session

    def create_many(self, results: list[HandsardSittingDateResult]) -> None:
        for result in results:
            self.session.add(result)
        self.session.commit()

    def get_all_sitting_dates(self) -> set[str]:
        return {r.sitting_date for r in self.session.exec(select(HandsardSittingDateResult)).all()}
