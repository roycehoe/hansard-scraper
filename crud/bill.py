from sqlmodel import Session, col, func, select

from database.bill import Bill


class CRUDBill:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, bills: list[Bill]) -> None:
        self.session.add_all(bills)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(Bill)
        return self.session.exec(statement).one()

    def get_count_by_is_passed(self, is_passed: bool) -> int:
        statement = (
            select(func.count())
            .select_from(Bill)
            .where(col(Bill.is_passed).is_(is_passed))
        )
        return self.session.exec(statement).one()
