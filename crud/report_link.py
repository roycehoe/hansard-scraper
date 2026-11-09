from dataclasses import dataclass

from sqlmodel import Session, delete, select

from database.report_link import ReportLink
from enums import ReportLinkRule, ReportLinkType


@dataclass(frozen=True)
class ReportLinkRow:
    id: int
    link_type: ReportLinkType
    rule: ReportLinkRule
    printed_citation: str
    source_report_id: str
    target_report_id: str


class CRUDReportLink:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, report_links: list[ReportLink]) -> None:
        self.session.add_all(report_links)
        self.session.flush()

    def get_rows(self) -> list[ReportLinkRow]:
        statement = select(
            ReportLink.id,
            ReportLink.link_type,
            ReportLink.rule,
            ReportLink.printed_citation,
            ReportLink.source_report_id,
            ReportLink.target_report_id,
        ).order_by(ReportLink.id)
        return [ReportLinkRow(*row) for row in self.session.exec(statement).all()]

    def delete_all(self) -> int:
        statement = delete(ReportLink)

        return self.session.exec(statement).rowcount
