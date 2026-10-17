from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import text
from sqlmodel import Session, col, delete, func, select

from database.report import Report
from database.speech import Speech

_STREAM_BATCH = 10_000


@dataclass(frozen=True)
class SpeechRow:
    id: int
    ordinal: int
    speaker: Optional[str]
    transcript: str
    report_id: int
    speaker_id: Optional[int]


@dataclass(frozen=True)
class SpeechSpeakerRow:
    id: int
    speaker: Optional[str]
    parliament_number: int
    sitting_date: datetime


@dataclass(frozen=True)
class SpeechReportTypeRow:
    speaker: str
    report_type: str
    parliament_number: int


@dataclass(frozen=True)
class SpeechParliamentRow:
    id: int
    speaker: str
    report_type: str
    parliament_number: int


@dataclass(frozen=True)
class SpeechLinkRow:
    report_id: int
    ordinal: int
    speaker: Optional[str]
    speaker_id: int
    transcript: str


@dataclass(frozen=True)
class SpeakerStringCount:
    speaker: str
    row_count: int


class CRUDSpeech:
    def __init__(self, session: Session):
        self.session = session

    def create(self, speech: Speech) -> None:
        self.session.add(speech)
        self.session.commit()

    def create_many(self, speeches: list[Speech]) -> None:
        self.session.add_all(speeches)
        self.session.commit()

    def get_distinct_report_ids(self) -> set[int]:
        statement = select(Speech.report_id).distinct()
        return set(self.session.exec(statement).all()) - {None}

    def get_speaker_rows_by_speaker_not_null(self) -> list[SpeechReportTypeRow]:
        statement = (
            select(Speech.speaker, Report.report_type, Report.parliament_number)
            .join(Report, Report.id == Speech.report_id)
            .where(Speech.speaker.is_not(None))
        )
        return [SpeechReportTypeRow(*row) for row in self.session.exec(statement).all()]

    def get_speaker_rows_by_speaker_id_null(self) -> Iterable[SpeechSpeakerRow]:
        statement = (
            select(Speech.id, Speech.speaker, Report.parliament_number, Report.sitting_date)
            .join(Report)
            .where(col(Speech.speaker_id).is_(None))
            .execution_options(yield_per=_STREAM_BATCH)
        )
        return (SpeechSpeakerRow(*row) for row in self.session.exec(statement))

    def get_link_rows_by_speaker_id_not_null(self) -> Iterable[SpeechLinkRow]:
        statement = (
            select(Speech.report_id, Speech.ordinal, Speech.speaker, Speech.speaker_id, Speech.transcript)
            .where(col(Speech.speaker_id).is_not(None))
            .execution_options(yield_per=_STREAM_BATCH)
        )
        return (SpeechLinkRow(*row) for row in self.session.exec(statement))

    def get_speaker_counts_by_speaker_id_null_and_speaker_not_null(self) -> list[SpeakerStringCount]:
        statement = (
            select(Speech.speaker, func.count())
            .where(col(Speech.speaker_id).is_(None))
            .where(col(Speech.speaker).is_not(None))
            .group_by(Speech.speaker)
        )
        return [SpeakerStringCount(*row) for row in self.session.exec(statement).all()]

    def get_report_ids_by_speaker_id_null_and_speaker_regex(self, pattern: str) -> list[int]:
        statement = (
            select(Speech.report_id)
            .distinct()
            .where(col(Speech.speaker_id).is_(None))
            .where(Speech.speaker.regexp_match(pattern, flags="i"))
        )
        return list(self.session.exec(statement).all())

    def get_rows_by_report_ids(self, report_ids: list[int]) -> list[SpeechRow]:
        statement = (
            select(Speech.id, Speech.ordinal, Speech.speaker, Speech.transcript, Speech.report_id, Speech.speaker_id)
            .where(col(Speech.report_id).in_(report_ids))
            .order_by(Speech.report_id, Speech.ordinal)
        )
        return [SpeechRow(*row) for row in self.session.exec(statement).all()]

    def get_speaker_ids_by_ids(self, speech_ids: list[int]) -> dict[int, Optional[int]]:
        statement = select(Speech.id, Speech.speaker_id).where(col(Speech.id).in_(speech_ids))
        return {speech_id: speaker_id for speech_id, speaker_id in self.session.exec(statement).all()}

    def get_speaker_ids_by_ids_for_update(self, speech_ids: list[int]) -> dict[int, Optional[int]]:
        statement = select(Speech.id, Speech.speaker_id).where(col(Speech.id).in_(speech_ids)).with_for_update()
        return {speech_id: speaker_id for speech_id, speaker_id in self.session.exec(statement).all()}

    def get_speaker_rows_by_ids(self, speech_ids: list[int]) -> list[SpeechSpeakerRow]:
        statement = (
            select(Speech.id, Speech.speaker, Report.parliament_number, Report.sitting_date)
            .join(Report)
            .where(Speech.id.in_(speech_ids))
        )
        return [SpeechSpeakerRow(*row) for row in self.session.exec(statement).all()]

    def get_speaker_rows_by_speaker_not_null_and_parliament_number(self, parliament_number: int) -> list[SpeechParliamentRow]:
        statement = (
            select(Speech.id, Speech.speaker, Report.report_type, Report.parliament_number)
            .join(Report)
            .where(Speech.speaker.is_not(None))
            .where(Report.parliament_number == parliament_number)
        )
        return [SpeechParliamentRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_report_id(self, report_id: int) -> int:
        statement = delete(Speech).where(Speech.report_id == report_id)
        delete_result = self.session.exec(statement)
        self.session.commit()
        return delete_result.rowcount

    def delete_by_report_ids(self, report_ids: list[int]) -> int:
        statement = delete(Speech).where(col(Speech.report_id).in_(report_ids))
        return self.session.exec(statement).rowcount

    def set_speaker_ids_bulk(self, updates: dict[int, Optional[int]]) -> None:
        if not updates:
            return
        self.session.execute(
            text(
                "UPDATE speech SET speaker_id = v.speaker_id "
                "FROM UNNEST(:ids, CAST(:speaker_ids AS integer[])) AS v(id, speaker_id) "
                "WHERE speech.id = v.id"
            ),
            {"ids": list(updates.keys()), "speaker_ids": list(updates.values())},
        )
