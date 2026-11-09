from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional, Sequence

import sqlalchemy
from sqlalchemy import SQLColumnExpression, not_, text
from sqlmodel import Session, col, delete, exists, func, select

from database.report import Report
from database.report_participant import ReportParticipant
from database.report_question_state import ReportQuestionState
from enums import ParticipantRole, QuestionState, ReportType
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
class ReportSittingDateTitleRow:
    id: int
    sitting_date: datetime
    title: str


@dataclass(frozen=True)
class ReportPlacementRow:
    id: int
    report_id: str
    sitting_date: datetime
    title: str
    report_type: str


@dataclass(frozen=True)
class ReportFrameRow:
    id: int
    report_id: int
    parliament_number: int
    report_version: str
    report_type: str
    sitting_date: datetime
    sprs_report_id: str
    first_ordinal: Optional[int]
    speaker_id: Optional[int]
    printed_name: Optional[str]


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


@dataclass(frozen=True)
class ReportAskerReportRow:
    id: int
    parliament_number: int
    sitting_date: datetime
    title: str


@dataclass(frozen=True)
class ReportLinkReportRow:
    id: int
    report_id: str
    report_type: str
    report_version: str
    sitting_date: datetime
    original_title: str
    title: str
    html_file_name: Optional[str]


@dataclass(frozen=True)
class ReportContentRow:
    id: int
    content: Optional[str]


@dataclass(frozen=True)
class ReportDivisionRow:
    id: int
    report_id: str
    parliament_number: int
    sitting_date: datetime


@dataclass(frozen=True)
class ReportParticipantReportRow:
    id: int
    parliament_number: int
    sitting_date: datetime
    title: str
    mps_speaking_header: Optional[str]


@dataclass(frozen=True)
class ReportPutToReportRow:
    id: int
    report_id: str
    sitting_date: datetime


_STREAM_BATCH = 200
_MPS_SPEAKING_HEADER_PATTERN = r"MPs Speaking:\|?([^\n]*)"


@dataclass(frozen=True)
class ReportTitleRow:
    id: int
    original_title: str
    title: str
    subtitle: Optional[str]


@dataclass(frozen=True)
class AttachedFileReportRow:
    id: int
    report_id: str
    content: Optional[str]


def _get_frame_order_columns() -> list[SQLColumnExpression]:
    return [
        col(Report.parliament_number),
        col(Report.report_version).collate("C"),
        col(Report.report_type).collate("C"),
        col(Report.sitting_date),
        col(Report.report_id).collate("C"),
    ]


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

    def get_ids(self) -> list[int]:
        statement = select(col(Report.id)).order_by(col(Report.id))
        return list(self.session.exec(statement).all())

    def get_ids_by_report_types(self, report_types: Sequence[str]) -> list[int]:
        statement = (
            select(col(Report.id))
            .where(col(Report.report_type).in_(report_types))
            .order_by(col(Report.id))
        )
        return list(self.session.exec(statement).all())

    def get_ids_by_markdown_content_not_null(self) -> list[int]:
        statement = (
            select(col(Report.id))
            .where(col(Report.markdown_content).is_not(None))
            .order_by(col(Report.id))
        )
        return list(self.session.exec(statement).all())

    def get_ids_by_content_regex(self, pattern: str) -> list[int]:
        statement = (
            select(col(Report.id))
            .where(col(Report.content).regexp_match(pattern))
            .order_by(col(Report.id))
        )
        return list(self.session.exec(statement).all())

    def get_by_ids(self, report_ids: list[int]) -> list[Report]:
        statement = (
            select(Report)
            .where(col(Report.id).in_(report_ids))
            .order_by(col(Report.id))
        )
        return list(self.session.exec(statement).all())

    def get_by_ids_for_update(self, report_ids: list[int]) -> list[Report]:
        statement = (
            select(Report).where(col(Report.id).in_(report_ids)).with_for_update()
        )
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

    def get_distinct_sitting_dates_by_sitting_date_from(
        self, first_sitting_date: datetime
    ) -> list[datetime]:
        statement = (
            select(Report.sitting_date)
            .where(col(Report.sitting_date) >= first_sitting_date)
            .distinct()
            .order_by(col(Report.sitting_date))
        )
        return list(self.session.exec(statement).all())

    def get_max_parliament_number(self) -> Optional[int]:
        statement = select(func.max(Report.parliament_number))
        return self.session.exec(statement).one()

    def get_report_ids_by_sitting_date_from(
        self, first_sitting_date: datetime
    ) -> set[str]:
        statement = select(Report.report_id).where(
            col(Report.sitting_date) >= first_sitting_date
        )
        return set(self.session.exec(statement).all())

    def get_max_sitting_date_by_content_not_null_and_content_not_empty(
        self,
    ) -> Optional[datetime]:
        statement = (
            select(func.max(Report.sitting_date))
            .where(col(Report.content).is_not(None))
            .where(Report.content != "")
        )
        return self.session.exec(statement).one()

    def get_header_rows(self) -> list[ReportHeaderRow]:
        statement = select(
            Report.id,
            Report.report_type,
            Report.parliament_number,
            Report.sitting_date,
            Report.title,
        )
        return [ReportHeaderRow(*row) for row in self.session.exec(statement).all()]

    def get_sitting_date_title_rows_by_report_types(
        self, report_types: tuple[ReportType, ...]
    ) -> list[ReportSittingDateTitleRow]:
        statement = (
            select(Report.id, Report.sitting_date, Report.title)
            .where(col(Report.report_type).in_(report_types))
            .order_by(col(Report.sitting_date), col(Report.id))
        )
        return [
            ReportSittingDateTitleRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def get_sitting_date_title_rows_by_report_types_not_in_and_title_regex(
        self, report_types: tuple[ReportType, ...], pattern: str
    ) -> list[ReportSittingDateTitleRow]:
        statement = (
            select(Report.id, Report.sitting_date, Report.title)
            .where(not_(col(Report.report_type).in_(report_types)))
            .where(col(Report.title).regexp_match(pattern, flags="i"))
            .order_by(col(Report.sitting_date), col(Report.id))
        )
        return [
            ReportSittingDateTitleRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def get_placement_rows_by_report_types(
        self, report_types: tuple[ReportType, ...]
    ) -> list[ReportPlacementRow]:
        statement = (
            select(
                Report.id,
                Report.report_id,
                Report.sitting_date,
                Report.title,
                Report.report_type,
            )
            .where(col(Report.report_type).in_(report_types))
            .order_by(col(Report.sitting_date), col(Report.id))
        )
        return [ReportPlacementRow(*row) for row in self.session.exec(statement).all()]

    def get_placement_rows_by_report_types_not_in_and_title_regex(
        self, report_types: tuple[ReportType, ...], pattern: str
    ) -> list[ReportPlacementRow]:
        statement = (
            select(
                Report.id,
                Report.report_id,
                Report.sitting_date,
                Report.title,
                Report.report_type,
            )
            .where(not_(col(Report.report_type).in_(report_types)))
            .where(col(Report.title).regexp_match(pattern, flags="i"))
            .order_by(col(Report.sitting_date), col(Report.id))
        )
        return [ReportPlacementRow(*row) for row in self.session.exec(statement).all()]

    def get_sitting_date_title_rows_by_ids(
        self, report_ids: list[int]
    ) -> list[ReportSittingDateTitleRow]:
        statement = (
            select(Report.id, Report.sitting_date, Report.title)
            .where(col(Report.id).in_(report_ids))
            .order_by(col(Report.sitting_date), col(Report.id))
        )
        return [
            ReportSittingDateTitleRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def get_placement_rows_by_ids(
        self, report_ids: list[int]
    ) -> list[ReportPlacementRow]:
        statement = (
            select(
                Report.id,
                Report.report_id,
                Report.sitting_date,
                Report.title,
                Report.report_type,
            )
            .where(col(Report.id).in_(report_ids))
            .order_by(col(Report.sitting_date), col(Report.id))
        )
        return [ReportPlacementRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_ids(self, report_ids: list[int]) -> int:
        statement = delete(Report).where(col(Report.id).in_(report_ids))

        return self.session.exec(statement).rowcount

    def get_title_rows(self) -> list[ReportTitleRow]:
        statement = select(
            Report.id, Report.original_title, Report.title, Report.subtitle
        ).order_by(Report.id)
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
            select(
                Report.id,
                Report.title,
                Report.subtitle,
                Report.content,
                Report.markdown_content,
            )
            .order_by(Report.id)
            .execution_options(yield_per=_STREAM_BATCH)
        )
        return (ReportTextRow(*row) for row in self.session.exec(statement))

    def get_markdown_rows_by_markdown_content_regex(
        self, pattern: str
    ) -> list[ReportMarkdownRow]:
        statement = (
            select(Report.id, Report.sitting_date, Report.markdown_content)
            .where(col(Report.markdown_content).regexp_match(pattern))
            .order_by(Report.id)
        )
        return [ReportMarkdownRow(*row) for row in self.session.exec(statement).all()]

    def set_markdown_contents_bulk_by_markdown_content(
        self, text_changes: list[TextChange]
    ) -> int:
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

    def set_sitting_numbers_bulk(
        self, report_id_to_sitting_number: dict[int, int]
    ) -> int:
        if not report_id_to_sitting_number:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE report SET sitting_number = v.sitting_number "
                "FROM UNNEST(:ids, :sitting_numbers) AS v(id, sitting_number) "
                "WHERE report.id = v.id"
            ),
            {
                "ids": list(report_id_to_sitting_number.keys()),
                "sitting_numbers": list(report_id_to_sitting_number.values()),
            },
        )

        return update_result.rowcount

    def get_column_rows_by_ids(self, report_ids: list[int]) -> list[ReportColumnRow]:
        statement = (
            select(
                Report.id,
                Report.parliament_number,
                Report.column_start,
                Report.column_end,
            )
            .where(col(Report.id).in_(report_ids))
            .order_by(Report.id)
        )
        return [ReportColumnRow(*row) for row in self.session.exec(statement).all()]

    def get_link_report_rows(self) -> list[ReportLinkReportRow]:
        statement = select(
            Report.id,
            Report.report_id,
            Report.report_type,
            Report.report_version,
            Report.sitting_date,
            Report.original_title,
            Report.title,
            Report.html_file_name,
        ).order_by(Report.id)
        return [ReportLinkReportRow(*row) for row in self.session.exec(statement).all()]

    def get_asker_report_rows_by_report_types(
        self, report_types: Sequence[str]
    ) -> list[ReportAskerReportRow]:
        statement = (
            select(
                Report.id, Report.parliament_number, Report.sitting_date, Report.title
            )
            .where(col(Report.report_type).in_(report_types))
            .order_by(Report.id)
        )
        return [
            ReportAskerReportRow(*row) for row in self.session.exec(statement).all()
        ]

    def get_asker_report_rows_by_ids_and_report_types(
        self, report_ids: list[int], report_types: Sequence[str]
    ) -> list[ReportAskerReportRow]:
        statement = (
            select(
                Report.id, Report.parliament_number, Report.sitting_date, Report.title
            )
            .where(col(Report.id).in_(report_ids))
            .where(col(Report.report_type).in_(report_types))
            .order_by(Report.id)
        )
        return [
            ReportAskerReportRow(*row) for row in self.session.exec(statement).all()
        ]

    def get_division_report_rows_by_ids(
        self, report_ids: list[int]
    ) -> list[ReportDivisionRow]:
        statement = (
            select(
                Report.id, Report.report_id, Report.parliament_number, Report.sitting_date
            )
            .where(col(Report.id).in_(report_ids))
            .order_by(col(Report.id))
        )
        return [ReportDivisionRow(*row) for row in self.session.exec(statement).all()]

    def get_content_rows_by_ids(self, report_ids: list[int]) -> list[ReportContentRow]:
        statement = (
            select(Report.id, Report.content)
            .where(col(Report.id).in_(report_ids))
            .order_by(col(Report.id))
        )
        return [ReportContentRow(*row) for row in self.session.exec(statement).all()]

    def get_participant_report_rows_by_ids_and_report_types(
        self, report_ids: list[int], report_types: Sequence[str]
    ) -> list[ReportParticipantReportRow]:
        statement = (
            select(
                Report.id,
                Report.parliament_number,
                Report.sitting_date,
                Report.title,
                func.substring(Report.markdown_content, _MPS_SPEAKING_HEADER_PATTERN),
            )
            .where(col(Report.id).in_(report_ids))
            .where(col(Report.report_type).in_(report_types))
            .order_by(Report.id)
        )
        return [
            ReportParticipantReportRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def get_put_to_report_rows_by_ids_and_report_types(
        self, report_ids: list[int], report_types: Sequence[str]
    ) -> list[ReportPutToReportRow]:
        statement = (
            select(Report.id, Report.report_id, Report.sitting_date)
            .where(col(Report.id).in_(report_ids))
            .where(col(Report.report_type).in_(report_types))
            .order_by(Report.id)
        )
        return [
            ReportPutToReportRow(*row) for row in self.session.exec(statement).all()
        ]

    def set_column_ranges_bulk(
        self, report_column_ranges: list[ReportColumnRange]
    ) -> int:
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
                "ids": [
                    report_column_range.id
                    for report_column_range in report_column_ranges
                ],
                "column_starts": [
                    report_column_range.column_start
                    for report_column_range in report_column_ranges
                ],
                "column_ends": [
                    report_column_range.column_end
                    for report_column_range in report_column_ranges
                ],
            },
        )

        return update_result.rowcount

    def get_vacuum_count(self) -> int:
        statement = text(
            "SELECT vacuum_count FROM pg_stat_user_tables WHERE relid = 'report'::regclass"
        )
        return self.session.execute(statement).scalar_one()

    # NOTE: the commit hands the autocommit connection back, so the session's next statement runs in a transaction
    def vacuum_analyze(self) -> None:
        statement = text("VACUUM (ANALYZE) report")
        self.session.connection(
            execution_options={"isolation_level": "AUTOCOMMIT"}
        ).execute(statement)
        self.session.commit()

    # NOTE: SQLModel's select types at most four columns, and session.exec takes no other select, so the frame reads below use SQLAlchemy's select with session.execute
    def get_frame_rows_by_participant_role(
        self, role: ParticipantRole
    ) -> list[ReportFrameRow]:
        statement = (
            sqlalchemy.select(
                col(ReportParticipant.id),
                col(Report.id),
                col(Report.parliament_number),
                col(Report.report_version),
                col(Report.report_type),
                col(Report.sitting_date),
                col(Report.report_id),
                col(ReportParticipant.first_ordinal),
                col(ReportParticipant.speaker_id),
                col(ReportParticipant.printed_name),
            )
            .join(ReportParticipant, col(ReportParticipant.report_id) == Report.id)
            .where(col(ReportParticipant.role) == role)
            .order_by(
                *_get_frame_order_columns(),
                col(ReportParticipant.first_ordinal),
                col(ReportParticipant.id),
            )
        )
        return [ReportFrameRow(*row) for row in self.session.execute(statement).all()]

    def get_frame_rows_by_participant_role_and_first_ordinal_above_report_minimum(
        self, role: ParticipantRole
    ) -> list[ReportFrameRow]:
        report_minimum = (
            select(
                ReportParticipant.report_id,
                func.min(ReportParticipant.first_ordinal).label("minimum_ordinal"),
            )
            .where(ReportParticipant.role == role)
            .group_by(col(ReportParticipant.report_id))
            .subquery()
        )
        statement = (
            sqlalchemy.select(
                col(ReportParticipant.id),
                col(Report.id),
                col(Report.parliament_number),
                col(Report.report_version),
                col(Report.report_type),
                col(Report.sitting_date),
                col(Report.report_id),
                col(ReportParticipant.first_ordinal),
                col(ReportParticipant.speaker_id),
                col(ReportParticipant.printed_name),
            )
            .join(ReportParticipant, col(ReportParticipant.report_id) == Report.id)
            .join(
                report_minimum,
                report_minimum.c.report_id == ReportParticipant.report_id,
            )
            .where(col(ReportParticipant.role) == role)
            .where(ReportParticipant.first_ordinal > report_minimum.c.minimum_ordinal)
            .order_by(
                *_get_frame_order_columns(),
                col(ReportParticipant.first_ordinal),
                col(ReportParticipant.id),
            )
        )
        return [ReportFrameRow(*row) for row in self.session.execute(statement).all()]

    def get_frame_rows_by_question_state(
        self, state: QuestionState
    ) -> list[ReportFrameRow]:
        statement = (
            sqlalchemy.select(
                col(Report.id),
                col(Report.parliament_number),
                col(Report.report_version),
                col(Report.report_type),
                col(Report.sitting_date),
                col(Report.report_id),
            )
            .join(ReportQuestionState, col(ReportQuestionState.report_id) == Report.id)
            .where(col(ReportQuestionState.state) == state)
            .order_by(*_get_frame_order_columns(), col(Report.id))
        )
        return [
            ReportFrameRow(
                report_id,
                report_id,
                parliament_number,
                report_version,
                report_type,
                sitting_date,
                sprs_report_id,
                None,
                None,
                None,
            )
            for (
                report_id,
                parliament_number,
                report_version,
                report_type,
                sitting_date,
                sprs_report_id,
            ) in self.session.execute(statement).all()
        ]

    def get_frame_rows_by_participant_roles_present_and_participant_role_absent_and_question_state_absent(
        self, present_roles: list[ParticipantRole], absent_role: ParticipantRole
    ) -> list[ReportFrameRow]:
        statement = (
            sqlalchemy.select(
                col(Report.id),
                col(Report.parliament_number),
                col(Report.report_version),
                col(Report.report_type),
                col(Report.sitting_date),
                col(Report.report_id),
            )
            .where(
                exists().where(
                    col(ReportParticipant.report_id) == Report.id,
                    col(ReportParticipant.role).in_(present_roles),
                )
            )
            .where(
                ~exists().where(
                    col(ReportParticipant.report_id) == Report.id,
                    col(ReportParticipant.role) == absent_role,
                )
            )
            .where(~exists().where(col(ReportQuestionState.report_id) == Report.id))
            .order_by(*_get_frame_order_columns(), col(Report.id))
        )
        return [
            ReportFrameRow(
                report_id,
                report_id,
                parliament_number,
                report_version,
                report_type,
                sitting_date,
                sprs_report_id,
                None,
                None,
                None,
            )
            for (
                report_id,
                parliament_number,
                report_version,
                report_type,
                sitting_date,
                sprs_report_id,
            ) in self.session.execute(statement).all()
        ]

    def get_attached_file_report_rows_by_ids(
        self, report_ids: list[int]
    ) -> list[AttachedFileReportRow]:
        statement = (
            select(Report.id, Report.report_id, Report.content)
            .where(col(Report.id).in_(report_ids))
            .order_by(Report.id)
        )
        return [
            AttachedFileReportRow(*row) for row in self.session.exec(statement).all()
        ]
