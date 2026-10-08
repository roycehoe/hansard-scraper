from typing import Optional

from sqlmodel import Session, select

from database.hansard_sitting_date_response import HansardSittingDateResponse


class CRUDHansardSittingDateResponse:
    def __init__(self, session: Session):
        self.session = session

    def create(self, response: HansardSittingDateResponse) -> None:
        self.session.add(response)
        self.session.commit()

    def get_all(self) -> list[HansardSittingDateResponse]:
        return list(self.session.exec(select(HansardSittingDateResponse)).all())

    def get_all_sitting_dates(self) -> set[str]:
        return set(self.session.exec(select(HansardSittingDateResponse.sitting_date)).all())

    def get_by_sitting_date(self, sitting_date: str) -> Optional[HansardSittingDateResponse]:
        return self.session.exec(
            select(HansardSittingDateResponse).where(HansardSittingDateResponse.sitting_date == sitting_date)
        ).first()
