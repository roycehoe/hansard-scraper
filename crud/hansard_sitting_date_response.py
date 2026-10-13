from typing import Optional

from sqlmodel import Session, select

from database.hansard_sitting_date_response import HansardSittingDateResponse


class CRUDHansardSittingDateResponse:
    def __init__(self, session: Session):
        self.session = session

    def create(self, response: HansardSittingDateResponse) -> None:
        self.session.add(response)
        self.session.commit()

    def update(self, response: HansardSittingDateResponse) -> None:
        self.session.add(response)
        self.session.flush()

    def get_all(self) -> list[HansardSittingDateResponse]:
        statement = select(HansardSittingDateResponse)
        return list(self.session.exec(statement).all())

    def get_all_sitting_dates(self) -> set[str]:
        statement = select(HansardSittingDateResponse.sitting_date)
        return set(self.session.exec(statement).all())

    def get_by_sitting_date(self, sitting_date: str) -> Optional[HansardSittingDateResponse]:
        statement = select(HansardSittingDateResponse).where(HansardSittingDateResponse.sitting_date == sitting_date)
        return self.session.exec(statement).first()
