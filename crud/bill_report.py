from dataclasses import dataclass

from sqlmodel import Session, col, delete, func, select

from database.bill import BillReport


@dataclass(frozen=True)
class BillReportRow:
    bill_id: int
    report_id: int


class CRUDBillReport:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, bill_reports: list[BillReport]) -> None:
        self.session.add_all(bill_reports)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(BillReport)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[BillReportRow]:
        statement = select(BillReport.bill_id, BillReport.report_id).order_by(
            col(BillReport.bill_id), col(BillReport.id)
        )
        return [BillReportRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_bill_ids(self, bill_ids: list[int]) -> None:
        if not bill_ids:
            return

        statement = delete(BillReport).where(col(BillReport.bill_id).in_(bill_ids))
        self.session.execute(statement)
