from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import text
from sqlmodel import Session, col, func, select

from database.sitting import Sitting
from utils.text import TextChange


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


@dataclass(frozen=True)
class SittingTextRow:
    id: int
    html_full_content: Optional[str]
    markdown_content: Optional[str]


@dataclass(frozen=True)
class SittingDateMarkdownRow:
    sitting_date: str
    markdown_content: str


@dataclass(frozen=True)
class SittingDateSectionsRow:
    sitting_date: str
    sections: str


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

    def get_sitting_dates_by_sitting_date_not_null(self) -> set[str]:
        statement = select(Sitting.sitting_date).where(Sitting.sitting_date.is_not(None))
        return set(self.session.exec(statement).all())

    def get_max_parlement_no(self) -> Optional[int]:
        statement = select(func.max(Sitting.parlement_no))
        return self.session.exec(statement).one()

    def get_date_markdown_rows_by_sitting_dates_and_markdown_content_not_null(self, sitting_dates: list[str]) -> list[SittingDateMarkdownRow]:
        statement = (
            select(Sitting.sitting_date, Sitting.markdown_content)
            .where(col(Sitting.sitting_date).in_(sitting_dates))
            .where(Sitting.markdown_content.is_not(None))
        )
        return [SittingDateMarkdownRow(*row) for row in self.session.exec(statement).all()]

    def get_date_sections_rows_by_sitting_dates_and_sections_not_null(self, sitting_dates: list[str]) -> list[SittingDateSectionsRow]:
        statement = (
            select(Sitting.sitting_date, Sitting.sections)
            .where(col(Sitting.sitting_date).in_(sitting_dates))
            .where(Sitting.sections.is_not(None))
        )
        return [SittingDateSectionsRow(*row) for row in self.session.exec(statement).all()]

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

    def get_text_rows(self) -> Iterable[SittingTextRow]:
        statement = (
            select(Sitting.id, Sitting.html_full_content, Sitting.markdown_content)
            .order_by(Sitting.id)
            .execution_options(yield_per=_STREAM_BATCH)
        )
        return (SittingTextRow(*row) for row in self.session.exec(statement))

    def get_markdown_rows_by_markdown_content_regex(self, pattern: str) -> list[SittingMarkdownRow]:
        statement = select(Sitting.id, Sitting.markdown_content).where(col(Sitting.markdown_content).regexp_match(pattern)).order_by(Sitting.id)
        return [SittingMarkdownRow(*row) for row in self.session.exec(statement).all()]

    def set_markdown_contents_bulk_by_markdown_content(self, text_changes: list[TextChange]) -> int:
        if not text_changes:
            return 0

        # NOTE: a row whose markdown is no longer the before text is left alone and not counted.
        update_result = self.session.execute(
            text(
                "UPDATE sitting SET markdown_content = v.after "
                "FROM UNNEST(CAST(:ids AS integer[]), CAST(:befores AS text[]), CAST(:afters AS text[])) AS v(id, before, after) "
                "WHERE sitting.id = v.id AND sitting.markdown_content = v.before"
            ),
            {
                "ids": [text_change.id for text_change in text_changes],
                "befores": [text_change.before for text_change in text_changes],
                "afters": [text_change.after for text_change in text_changes],
            },
        )

        return update_result.rowcount

    def set_session_numbers_bulk(self, sitting_id_to_session_number: dict[int, int]) -> int:
        if not sitting_id_to_session_number:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE sitting SET session_no = v.session_no "
                "FROM UNNEST(:ids, :session_numbers) AS v(id, session_no) "
                "WHERE sitting.id = v.id"
            ),
            {"ids": list(sitting_id_to_session_number.keys()), "session_numbers": list(sitting_id_to_session_number.values())},
        )

        return update_result.rowcount

    def set_sitting_numbers_bulk(self, sitting_id_to_sitting_number: dict[int, int]) -> int:
        if not sitting_id_to_sitting_number:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE sitting SET sitting_no = v.sitting_no "
                "FROM UNNEST(:ids, :sitting_numbers) AS v(id, sitting_no) "
                "WHERE sitting.id = v.id"
            ),
            {"ids": list(sitting_id_to_sitting_number.keys()), "sitting_numbers": list(sitting_id_to_sitting_number.values())},
        )

        return update_result.rowcount
