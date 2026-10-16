from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, col, delete, select

from database.report import Report


@dataclass(frozen=True)
class ReportHeaderRow:
    id: int
    report_type: str
    parliament_number: int
    sitting_date: datetime
    title: str


class CRUDReport:
    def __init__(self, session: Session):
        self.session = session

    def create(self, report: Report) -> None:
        self.session.add(report)
        self.session.commit()

    def create_many(self, reports: list[Report]) -> None:
        self.session.add_all(reports)
        self.session.commit()

    def get_all(self) -> list[Report]:
        statement = select(Report)
        return list(self.session.exec(statement).all())

    def update(self, report: Report) -> None:
        self.session.add(report)
        self.session.flush()

    def get_by_content_null(self) -> list[Report]:
        statement = select(Report).where(Report.content.is_(None))
        return list(self.session.exec(statement).all())

    def get_by_markdown_content_not_null(self) -> list[Report]:
        statement = select(Report).where(Report.markdown_content.is_not(None))
        return list(self.session.exec(statement).all())

    def get_by_ids(self, report_ids: list[int]) -> list[Report]:
        statement = select(Report).where(col(Report.id).in_(report_ids))
        return list(self.session.exec(statement).all())

    def get_by_report_ids(self, report_ids: list[str]) -> list[Report]:
        statement = select(Report).where(col(Report.report_id).in_(report_ids))
        return list(self.session.exec(statement).all())

    def get_by_sitting_dates(self, dates: list[datetime]) -> list[Report]:
        statement = select(Report).where(col(Report.sitting_date).in_(dates))
        return list(self.session.exec(statement).all())

    def get_all_report_ids(self) -> set[str]:
        statement = select(Report.report_id)
        return set(self.session.exec(statement).all())

    def get_header_rows(self) -> list[ReportHeaderRow]:
        statement = select(Report.id, Report.report_type, Report.parliament_number, Report.sitting_date, Report.title)
        return [ReportHeaderRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_ids(self, report_ids: list[int]) -> int:
        statement = delete(Report).where(col(Report.id).in_(report_ids))
        return self.session.exec(statement).rowcount
