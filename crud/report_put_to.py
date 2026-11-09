from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from database.report_put_to import ReportPutTo
from enums import ReportPutToSource


@dataclass(frozen=True)
class ReportPutToRow:
    id: int
    sprs_report_id: str
    ordinal: int
    office_printed: str
    source: ReportPutToSource


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

    def delete_by_sprs_report_ids(self, sprs_report_ids: list[str]) -> int:
        statement = delete(ReportPutTo).where(
            col(ReportPutTo.sprs_report_id).in_(sprs_report_ids)
        )

        return self.session.exec(statement).rowcount
