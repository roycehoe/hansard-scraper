from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, delete, select

from database.report import Report
from database.report_put_to import ReportPutTo
from database.speech import Speech
from enums import ReportPutToSource


@dataclass(frozen=True)
class ReportPutToRow:
    id: int
    sprs_report_id: str
    ordinal: int
    office_printed: str
    source: ReportPutToSource


@dataclass(frozen=True)
class ReportPutToCheckRow:
    id: int
    sprs_report_id: str
    sitting_date: datetime
    report_type: str
    office_printed: str
    printed_text: str
    source: ReportPutToSource
    transcript: str


class CRUDReportPutTo:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, report_put_tos: list[ReportPutTo]) -> None:
        self.session.add_all(report_put_tos)
        self.session.flush()

    def get_rows_by_sprs_report_ids(
        self, sprs_report_ids: list[str]
    ) -> list[ReportPutToRow]:
        statement = (
            select(
                ReportPutTo.id,
                ReportPutTo.sprs_report_id,
                ReportPutTo.ordinal,
                ReportPutTo.office_printed,
                ReportPutTo.source,
            )
            .where(col(ReportPutTo.sprs_report_id).in_(sprs_report_ids))
            .order_by(ReportPutTo.sprs_report_id, ReportPutTo.ordinal)
        )
        return [ReportPutToRow(*row) for row in self.session.exec(statement).all()]

    def get_check_rows(self) -> list[ReportPutToCheckRow]:
        statement = (
            select(
                ReportPutTo.id,
                ReportPutTo.sprs_report_id,
                Report.sitting_date,
                Report.report_type,
                ReportPutTo.office_printed,
                ReportPutTo.printed_text,
                ReportPutTo.source,
                Speech.transcript,
            )
            .join(Report, col(Report.report_id) == ReportPutTo.sprs_report_id)
            .join(
                Speech,
                (col(Speech.report_id) == Report.id)
                & (col(Speech.ordinal) == ReportPutTo.first_ordinal),
            )
            .order_by(ReportPutTo.id)
        )
        return [ReportPutToCheckRow(*row) for row in self.session.exec(statement).all()]

    def get_distinct_office_printed(self) -> list[str]:
        statement = (
            select(ReportPutTo.office_printed)
            .distinct()
            .order_by(ReportPutTo.office_printed)
        )
        return list(self.session.exec(statement).all())

    def get_distinct_office_printed_by_sprs_report_ids(
        self, sprs_report_ids: list[str]
    ) -> list[str]:
        statement = (
            select(ReportPutTo.office_printed)
            .distinct()
            .where(col(ReportPutTo.sprs_report_id).in_(sprs_report_ids))
            .order_by(ReportPutTo.office_printed)
        )
        return list(self.session.exec(statement).all())

    def delete_by_sprs_report_ids(self, sprs_report_ids: list[str]) -> int:
        statement = delete(ReportPutTo).where(
            col(ReportPutTo.sprs_report_id).in_(sprs_report_ids)
        )

        return self.session.exec(statement).rowcount
