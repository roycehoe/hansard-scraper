from typing import Optional

from sqlmodel import Session, col, select

from database.hansard_sitting_date_response import HansardSittingDateResponse


class CRUDHansardSittingDateResponse:
    def __init__(self, session: Session):
        self.session = session

    def create(self, hansard_sitting_date_response: HansardSittingDateResponse) -> None:
        self.session.add(hansard_sitting_date_response)
        self.session.commit()

    def add_many(self, hansard_sitting_date_responses: list[HansardSittingDateResponse]) -> None:
        self.session.add_all(hansard_sitting_date_responses)
        self.session.flush()

    def update(self, hansard_sitting_date_response: HansardSittingDateResponse) -> None:
        self.session.add(hansard_sitting_date_response)
        self.session.flush()

    def get_all(self) -> list[HansardSittingDateResponse]:
        statement = select(HansardSittingDateResponse)
        return list(self.session.exec(statement).all())

    def get_sitting_dates_by_sitting_date_not_null(self) -> set[str]:
        statement = select(HansardSittingDateResponse.sitting_date).where(col(HansardSittingDateResponse.sitting_date).is_not(None))
        return set(self.session.exec(statement).all())

    def get_by_sitting_date(self, sitting_date: str) -> Optional[HansardSittingDateResponse]:
        statement = select(HansardSittingDateResponse).where(HansardSittingDateResponse.sitting_date == sitting_date)
        return self.session.exec(statement).first()
