from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import text
from sqlmodel import Session, col, delete, func, select

from database.report import Report
from utils.column_numbers import ReportColumnRange
from utils.text import TextChange


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
class ReportTextRow:
    id: int
    title: str
    subtitle: Optional[str]
    content: Optional[str]
    markdown_content: Optional[str]


@dataclass(frozen=True)
class ReportColumnRow:
    id: int
    parliament_number: int
    column_start: Optional[int]
    column_end: Optional[int]


_STREAM_BATCH = 200


@dataclass(frozen=True)
class ReportTitleRow:
    id: int
    original_title: str
    title: str
    subtitle: Optional[str]


class CRUDReport:
    def __init__(self, session: Session):
        self.session = session

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

    def get_ids_by_content_regex(self, pattern: str) -> list[int]:
        statement = select(col(Report.id)).where(col(Report.content).regexp_match(pattern)).order_by(col(Report.id))
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

    def get_by_sitting_dates(self, sitting_dates: list[datetime]) -> list[Report]:
        statement = select(Report).where(col(Report.sitting_date).in_(sitting_dates))
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

    def get_text_rows(self) -> Iterable[ReportTextRow]:
        statement = (
            select(Report.id, Report.title, Report.subtitle, Report.content, Report.markdown_content)
            .order_by(Report.id)
            .execution_options(yield_per=_STREAM_BATCH)
        )
        return (ReportTextRow(*row) for row in self.session.exec(statement))

    def get_markdown_rows_by_markdown_content_regex(self, pattern: str) -> list[ReportMarkdownRow]:
        statement = (
            select(Report.id, Report.sitting_date, Report.markdown_content)
            .where(col(Report.markdown_content).regexp_match(pattern))
            .order_by(Report.id)
        )
        return [ReportMarkdownRow(*row) for row in self.session.exec(statement).all()]

    def set_markdown_contents_bulk_by_markdown_content(self, text_changes: list[TextChange]) -> int:
        if not text_changes:
            return 0

        # NOTE: a row whose markdown is no longer the before text is left alone and not counted.
        update_result = self.session.execute(
            text(
                "UPDATE report SET markdown_content = v.after "
                "FROM UNNEST(CAST(:ids AS integer[]), CAST(:befores AS text[]), CAST(:afters AS text[])) AS v(id, before, after) "
                "WHERE report.id = v.id AND report.markdown_content = v.before"
            ),
            {
                "ids": [text_change.id for text_change in text_changes],
                "befores": [text_change.before for text_change in text_changes],
                "afters": [text_change.after for text_change in text_changes],
            },
        )

        return update_result.rowcount

    def set_sitting_numbers_bulk(self, report_id_to_sitting_number: dict[int, int]) -> int:
        if not report_id_to_sitting_number:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE report SET sitting_number = v.sitting_number "
                "FROM UNNEST(:ids, :sitting_numbers) AS v(id, sitting_number) "
                "WHERE report.id = v.id"
            ),
            {"ids": list(report_id_to_sitting_number.keys()), "sitting_numbers": list(report_id_to_sitting_number.values())},
        )

        return update_result.rowcount

    def get_column_rows_by_ids(self, report_ids: list[int]) -> list[ReportColumnRow]:
        statement = (
            select(Report.id, Report.parliament_number, Report.column_start, Report.column_end)
            .where(col(Report.id).in_(report_ids))
            .order_by(Report.id)
        )
        return [ReportColumnRow(*row) for row in self.session.exec(statement).all()]

    def set_column_ranges_bulk(self, report_column_ranges: list[ReportColumnRange]) -> int:
        if not report_column_ranges:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE report SET column_start = v.column_start, column_end = v.column_end "
                "FROM UNNEST(CAST(:ids AS integer[]), CAST(:column_starts AS integer[]), CAST(:column_ends AS integer[])) "
                "AS v(id, column_start, column_end) "
                "WHERE report.id = v.id"
            ),
            {
                "ids": [report_column_range.id for report_column_range in report_column_ranges],
                "column_starts": [report_column_range.column_start for report_column_range in report_column_ranges],
                "column_ends": [report_column_range.column_end for report_column_range in report_column_ranges],
            },
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
