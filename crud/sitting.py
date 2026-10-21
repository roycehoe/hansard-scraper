from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import text
from sqlmodel import Session, col, func, select

from database.sitting import Sitting


@dataclass(frozen=True)
class SittingDateRow:
    id: int
    sitting_date: Optional[str]
    parlement_no: Optional[int]
    volume_no: Optional[int]


@dataclass(frozen=True)
class SittingNumberRow:
    id: int
    sitting_date: Optional[str]
    session_no: Optional[int]
    sitting_no: Optional[int]
    markdown_content: Optional[str]


@dataclass(frozen=True)
class SittingMarkdownRow:
    id: int
    markdown_content: str


_STREAM_BATCH = 50


class CRUDSitting:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sitting: Sitting) -> None:
        self.session.add(sitting)
        self.session.commit()

    def create_many(self, sittings: list[Sitting]) -> None:
        self.session.add_all(sittings)
        self.session.commit()

    def add_many(self, sittings: list[Sitting]) -> None:
        self.session.add_all(sittings)
        self.session.flush()

    def update(self, sitting: Sitting) -> None:
        self.session.add(sitting)
        self.session.flush()

    def get_all(self) -> list[Sitting]:
        statement = select(Sitting)
        return list(self.session.exec(statement).all())

    def get_by_html_full_content_null_and_sections_null(self) -> list[Sitting]:
        statement = (
            select(Sitting)
            .where(Sitting.html_full_content.is_(None))
            .where(Sitting.sections.is_(None))
        )
        return list(self.session.exec(statement).all())

    def get_all_sitting_dates(self) -> set[str]:
        statement = select(Sitting.sitting_date)
        sitting_dates = self.session.exec(statement).all()
        return {sitting_date for sitting_date in sitting_dates if sitting_date is not None}

    def get_max_parlement_no(self) -> Optional[int]:
        statement = select(func.max(Sitting.parlement_no))
        return self.session.exec(statement).one()

    def get_markdown_by_dates(self, dates: list[str]) -> dict[str, str]:
        statement = (
            select(Sitting.sitting_date, Sitting.markdown_content)
            .where(col(Sitting.sitting_date).in_(dates))
            .where(Sitting.markdown_content.is_not(None))
        )
        sitting_markdown_rows = self.session.exec(statement).all()
        return {sitting_date: markdown for sitting_date, markdown in sitting_markdown_rows}

    def get_sections_by_dates(self, dates: list[str]) -> dict[str, str]:
        statement = (
            select(Sitting.sitting_date, Sitting.sections)
            .where(col(Sitting.sitting_date).in_(dates))
            .where(Sitting.sections.is_not(None))
        )
        sitting_sections_rows = self.session.exec(statement).all()
        return {sitting_date: sections for sitting_date, sections in sitting_sections_rows}

    def get_date_rows(self) -> list[SittingDateRow]:
        statement = select(Sitting.id, Sitting.sitting_date, Sitting.parlement_no, Sitting.volume_no)
        return [SittingDateRow(*row) for row in self.session.exec(statement).all()]

    def get_number_rows(self) -> Iterable[SittingNumberRow]:
        statement = (
            select(Sitting.id, Sitting.sitting_date, Sitting.session_no, Sitting.sitting_no, Sitting.markdown_content)
            .order_by(Sitting.id)
            .execution_options(yield_per=_STREAM_BATCH)
        )
        return (SittingNumberRow(*row) for row in self.session.exec(statement))

    def get_markdown_rows_by_markdown_content_regex(self, pattern: str) -> list[SittingMarkdownRow]:
        statement = select(Sitting.id, Sitting.markdown_content).where(col(Sitting.markdown_content).regexp_match(pattern)).order_by(Sitting.id)
        return [SittingMarkdownRow(*row) for row in self.session.exec(statement).all()]

    def set_markdown_contents_bulk_by_markdown_content(self, updates: dict[int, tuple[str, str]]) -> int:
        if not updates:
            return 0
        # NOTE: each pair is (before, after); a row whose markdown is no longer the before text is left alone and not counted.
        update_result = self.session.execute(
            text(
                "UPDATE sitting SET markdown_content = v.after "
                "FROM UNNEST(CAST(:ids AS integer[]), CAST(:befores AS text[]), CAST(:afters AS text[])) AS v(id, before, after) "
                "WHERE sitting.id = v.id AND sitting.markdown_content = v.before"
            ),
            {"ids": list(updates), "befores": [before for before, _ in updates.values()], "afters": [after for _, after in updates.values()]},
        )
        return update_result.rowcount

    def set_session_numbers_bulk(self, updates: dict[int, int]) -> int:
        if not updates:
            return 0
        update_result = self.session.execute(
            text(
                "UPDATE sitting SET session_no = v.session_no "
                "FROM UNNEST(:ids, :session_numbers) AS v(id, session_no) "
                "WHERE sitting.id = v.id"
            ),
            {"ids": list(updates.keys()), "session_numbers": list(updates.values())},
        )
        return update_result.rowcount

    def set_sitting_numbers_bulk(self, updates: dict[int, int]) -> int:
        if not updates:
            return 0
        update_result = self.session.execute(
            text(
                "UPDATE sitting SET sitting_no = v.sitting_no "
                "FROM UNNEST(:ids, :sitting_numbers) AS v(id, sitting_no) "
                "WHERE sitting.id = v.id"
            ),
            {"ids": list(updates.keys()), "sitting_numbers": list(updates.values())},
        )
        return update_result.rowcount
