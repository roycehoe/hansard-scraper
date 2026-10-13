from datetime import datetime

from sqlmodel import Session, col, select

from database.report import Report


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

    def get_all_with_markdown(self) -> list[Report]:
        statement = select(Report).where(Report.markdown_content.is_not(None))
        return list(self.session.exec(statement).all())

    def get_by_ids(self, report_ids: list[int]) -> list[Report]:
        statement = select(Report).where(col(Report.id).in_(report_ids))
        return list(self.session.exec(statement).all())

    def get_by_sitting_dates(self, dates: list[datetime]) -> list[Report]:
        statement = select(Report).where(col(Report.sitting_date).in_(dates))
        return list(self.session.exec(statement).all())

    def get_all_report_ids(self) -> set[str]:
        statement = select(Report.report_id)
        return set(self.session.exec(statement).all())
