from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session, col, delete, select

from database.report_asker import ReportAsker
from enums import ReportAskerSource


@dataclass(frozen=True)
class ReportAskerRow:
    report_id: int
    source: ReportAskerSource
    speaker_id: Optional[int]
    reader_printed_name: Optional[str]
    ordinal: int
    printed_name: str
    reader_speaker_id: Optional[int]


class CRUDReportAsker:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, report_askers: list[ReportAsker]) -> None:
        self.session.add_all(report_askers)
        self.session.flush()

    def get_rows_by_report_ids(self, report_ids: list[int]) -> list[ReportAskerRow]:
        statement = (
            select(
                ReportAsker.report_id,
                ReportAsker.source,
                ReportAsker.speaker_id,
                ReportAsker.reader_printed_name,
                ReportAsker.ordinal,
                ReportAsker.printed_name,
                ReportAsker.reader_speaker_id,
            )
            .where(col(ReportAsker.report_id).in_(report_ids))
            .order_by(ReportAsker.report_id, ReportAsker.ordinal)
        )
        return [ReportAskerRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_report_ids(self, report_ids: list[int]) -> int:
        statement = delete(ReportAsker).where(
            col(ReportAsker.report_id).in_(report_ids)
        )

        return self.session.exec(statement).rowcount
