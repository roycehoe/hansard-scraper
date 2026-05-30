from datetime import datetime
from typing import Optional

from sqlmodel import Session, col, select

from database.report import Report


class CRUDReport:
    def __init__(self, session: Session):
        self.session = session

    def create(self, report: Report) -> None:
        self.session.add(report)
        self.session.commit()

    def get_all(self) -> list[Report]:
        return list(self.session.exec(select(Report)).all())

    def get_all_with_markdown(self) -> list[Report]:
        return list(self.session.exec(select(Report).where(Report.markdown_content.is_not(None))).all())

    def get_by_ids(self, ids: list[int]) -> list[Report]:
        return list(self.session.exec(select(Report).where(col(Report.id).in_(ids))).all())

    def get_first_filtered(
        self,
        *,
        sitting_date_before: Optional[datetime] = None,
        parliament_number: Optional[int] = None,
        report_type: Optional[str] = None,
        has_content: bool = False,
    ) -> Optional[Report]:
        filters = []
        if sitting_date_before is not None:
            filters.append(Report.sitting_date < sitting_date_before)
        if parliament_number is not None:
            filters.append(Report.parliament_number == parliament_number)
        if report_type is not None:
            filters.append(Report.report_type == report_type)
        if has_content:
            filters.append(Report.content.is_not(None))
        return self.session.exec(select(Report).where(*filters)).first()
