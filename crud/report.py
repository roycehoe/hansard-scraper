from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, col, delete, func, select

from database.report import Report


@dataclass(frozen=True)
class ReportHeaderRow:
    id: int
    report_type: str
    parliament_number: int
    sitting_date: datetime
    title: str


@dataclass(frozen=True)
class ReportMarkdownRow:
    id: int
    sitting_date: datetime
    markdown_content: Optional[str]


@dataclass(frozen=True)
class ReportTitleRow:
    id: int
    original_title: str
    title: str
    subtitle: Optional[str]


class CRUDReport:
    def __init__(self, session: Session):
        self.session = session

    def create(self, report: Report) -> None:
        self.session.add(report)
        self.session.commit()

    def create_many(self, reports: list[Report]) -> None:
        self.session.add_all(reports)
        self.session.commit()

    def add_many(self, reports: list[Report]) -> None:
        self.session.add_all(reports)
        self.session.flush()

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

    def get_ids_by_markdown_content_not_null(self) -> list[int]:
        statement = select(col(Report.id)).where(col(Report.markdown_content).is_not(None)).order_by(col(Report.id))
        return list(self.session.exec(statement).all())

    def get_by_ids(self, report_ids: list[int]) -> list[Report]:
        statement = select(Report).where(col(Report.id).in_(report_ids)).order_by(col(Report.id))
        return list(self.session.exec(statement).all())

    def get_by_ids_for_update(self, report_ids: list[int]) -> list[Report]:
        statement = select(Report).where(col(Report.id).in_(report_ids)).with_for_update()
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

    def get_max_parliament_number(self) -> Optional[int]:
        statement = select(func.max(Report.parliament_number))
        return self.session.exec(statement).one()

    def get_report_ids_by_sitting_date_from(self, first_sitting_date: datetime) -> set[str]:
        statement = select(Report.report_id).where(col(Report.sitting_date) >= first_sitting_date)
        return set(self.session.exec(statement).all())

    def get_max_sitting_date_by_content_not_null_and_content_not_empty(self) -> Optional[datetime]:
        statement = (
            select(func.max(Report.sitting_date))
            .where(col(Report.content).is_not(None))
            .where(Report.content != "")
        )
        return self.session.exec(statement).one()

    def get_header_rows(self) -> list[ReportHeaderRow]:
        statement = select(Report.id, Report.report_type, Report.parliament_number, Report.sitting_date, Report.title)
        return [ReportHeaderRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_ids(self, report_ids: list[int]) -> int:
        statement = delete(Report).where(col(Report.id).in_(report_ids))
        return self.session.exec(statement).rowcount

    def get_title_rows(self) -> list[ReportTitleRow]:
        statement = select(Report.id, Report.original_title, Report.title, Report.subtitle).order_by(Report.id)
        return [ReportTitleRow(*row) for row in self.session.exec(statement).all()]

    def get_markdown_rows_by_sitting_number_null(self) -> list[ReportMarkdownRow]:
        statement = (
            select(Report.id, Report.sitting_date, Report.markdown_content)
            .where(col(Report.sitting_number).is_(None))
            .order_by(Report.id)
        )
        return [ReportMarkdownRow(*row) for row in self.session.exec(statement).all()]

    def set_sitting_numbers_bulk(self, updates: dict[int, int]) -> int:
        if not updates:
            return 0
        update_result = self.session.execute(
            text(
                "UPDATE report SET sitting_number = v.sitting_number "
                "FROM UNNEST(:ids, :sitting_numbers) AS v(id, sitting_number) "
                "WHERE report.id = v.id"
            ),
            {"ids": list(updates.keys()), "sitting_numbers": list(updates.values())},
        )
        return update_result.rowcount

    def get_vacuum_count(self) -> int:
        statement = text("SELECT vacuum_count FROM pg_stat_user_tables WHERE relid = 'report'::regclass")
        return self.session.execute(statement).scalar_one()

    # NOTE: the commit hands the autocommit connection back, so the session's next statement runs in a transaction
    def vacuum_analyze(self) -> None:
        statement = text("VACUUM (ANALYZE) report")
        self.session.connection(execution_options={"isolation_level": "AUTOCOMMIT"}).execute(statement)
        self.session.commit()
