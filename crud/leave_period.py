from sqlmodel import Session, col, delete, func, select

from database.leave_period import LeavePeriod


class CRUDLeavePeriod:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, leave_periods: list[LeavePeriod]) -> None:
        self.session.add_all(leave_periods)
        self.session.flush()

    def get_by_period_keys(self, period_keys: list[str]) -> list[LeavePeriod]:
        statement = select(LeavePeriod).where(
            col(LeavePeriod.period_key).in_(period_keys)
        )
        return list(self.session.exec(statement).all())

    def get_count(self) -> int:
        statement = select(func.count()).select_from(LeavePeriod)
        return self.session.exec(statement).one()

    def delete_all(self) -> None:
        statement = delete(LeavePeriod)

        self.session.exec(statement)
