from sqlmodel import Session, func, select

from database.bill import BillReport


class CRUDBillReport:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, bill_reports: list[BillReport]) -> None:
        self.session.add_all(bill_reports)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(BillReport)
        return self.session.exec(statement).one()
