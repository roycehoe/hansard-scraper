from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, delete, func, select

from database.bill import BillReport
from database.report import Report
from enums import BillReportRole


@dataclass(frozen=True)
class BillReportRow:
    id: int
    bill_id: int
    report_id: int
    role: BillReportRole


@dataclass(frozen=True)
class BillReportSittingDateReportTypeRow:
    bill_id: int
    report_id: int
    sprs_report_id: str
    sitting_date: datetime
    report_type: str
    role: BillReportRole


class CRUDBillReport:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, bill_reports: list[BillReport]) -> None:
        self.session.add_all(bill_reports)
        self.session.flush()

    def get_count_by_role(self, role: BillReportRole) -> int:
        statement = (
            select(func.count()).select_from(BillReport).where(BillReport.role == role)
        )
        return self.session.exec(statement).one()

    def get_rows(self) -> list[BillReportRow]:
        statement = select(
            col(BillReport.id),
            col(BillReport.bill_id),
            col(BillReport.report_id),
            col(BillReport.role),
        ).order_by(col(BillReport.bill_id), col(BillReport.id))
        return [BillReportRow(*row) for row in self.session.execute(statement).all()]

    def get_sitting_date_report_type_rows(
        self,
    ) -> list[BillReportSittingDateReportTypeRow]:
        statement = (
            select(
                BillReport.bill_id,
                BillReport.report_id,
                Report.report_id,
                Report.sitting_date,
                Report.report_type,
                BillReport.role,
            )
            .select_from(BillReport)
            .join(Report, col(BillReport.report_id) == col(Report.id))
            .order_by(
                col(BillReport.bill_id), col(Report.sitting_date), col(Report.report_id)
            )
        )
        return [
            BillReportSittingDateReportTypeRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def get_sitting_date_report_type_rows_by_report_ids(
        self, report_ids: list[int]
    ) -> list[BillReportSittingDateReportTypeRow]:
        statement = (
            select(
                BillReport.bill_id,
                BillReport.report_id,
                Report.report_id,
                Report.sitting_date,
                Report.report_type,
                BillReport.role,
            )
            .select_from(BillReport)
            .join(Report, col(BillReport.report_id) == col(Report.id))
            .where(col(BillReport.report_id).in_(report_ids))
            .order_by(
                col(BillReport.bill_id), col(Report.sitting_date), col(Report.report_id)
            )
        )
        return [
            BillReportSittingDateReportTypeRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def delete_by_ids(self, ids: list[int]) -> None:
        if not ids:
            return

        statement = delete(BillReport).where(col(BillReport.id).in_(ids))
        self.session.execute(statement)

    def delete_by_bill_ids(self, bill_ids: list[int]) -> None:
        if not bill_ids:
            return

        statement = delete(BillReport).where(col(BillReport.bill_id).in_(bill_ids))
        self.session.execute(statement)
