from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import text
from sqlmodel import Session, col, delete, func, select

from database.report import Report
from database.speech import Speech
from enums import ColumnNote
from utils.column_numbers import SpeechColumnNote
from utils.text import TextChange

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
class SpeechSpeakerIdRow:
    id: int
    speaker_id: Optional[int]


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
class SpeechTranscriptRow:
    id: int
    transcript: str


@dataclass(frozen=True)
class SpeechLabelRow:
    id: int
    speaker: str


@dataclass(frozen=True)
class SpeechTextRow:
    id: int
    report_id: int
    speaker: Optional[str]
    transcript: str


@dataclass(frozen=True)
class SpeechColumnRow:
    id: int
    report_id: int
    speaker: Optional[str]
    transcript: str
    column_start: Optional[int]
    column_note: Optional[ColumnNote]
    column_suggested: Optional[int]


@dataclass(frozen=True)
class SpeakerStringCount:
    speaker: str
    row_count: int


class CRUDSpeech:
    def __init__(self, session: Session):
        self.session = session

    def create_many(self, speeches: list[Speech]) -> None:
        self.session.add_all(speeches)
        self.session.commit()

    def add_many(self, speeches: list[Speech]) -> None:
        self.session.add_all(speeches)
        self.session.flush()

    def get_distinct_report_ids(self) -> set[int]:
        statement = select(Speech.report_id).distinct()
        return set(self.session.exec(statement).all())

    def get_report_type_rows_by_speaker_not_null(self) -> list[SpeechReportTypeRow]:
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

    def get_speaker_rows_by_report_ids_and_speaker_id_null(self, report_ids: list[int]) -> list[SpeechSpeakerRow]:
        statement = (
            select(Speech.id, Speech.speaker, Report.parliament_number, Report.sitting_date)
            .join(Report)
            .where(col(Speech.report_id).in_(report_ids))
            .where(col(Speech.speaker_id).is_(None))
        )
        return [SpeechSpeakerRow(*row) for row in self.session.exec(statement).all()]

    def get_link_rows_by_speaker_id_not_null(self) -> Iterable[SpeechLinkRow]:
        statement = (
            select(Speech.report_id, Speech.ordinal, Speech.speaker, Speech.speaker_id, Speech.transcript)
            .where(col(Speech.speaker_id).is_not(None))
            .order_by(Speech.report_id, Speech.ordinal)
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

    def get_report_ids_by_report_ids_and_speaker_id_null_and_speaker_regex(self, report_ids: list[int], pattern: str) -> list[int]:
        statement = (
            select(Speech.report_id)
            .distinct()
            .where(col(Speech.report_id).in_(report_ids))
            .where(col(Speech.speaker_id).is_(None))
            .where(col(Speech.speaker).regexp_match(pattern, flags="i"))
        )
        return list(self.session.exec(statement).all())

    def get_rows_by_report_ids(self, report_ids: list[int]) -> list[SpeechRow]:
        statement = (
            select(Speech.id, Speech.ordinal, Speech.speaker, Speech.transcript, Speech.report_id, Speech.speaker_id)
            .where(col(Speech.report_id).in_(report_ids))
            .order_by(Speech.report_id, Speech.ordinal)
        )
        return [SpeechRow(*row) for row in self.session.exec(statement).all()]

    def get_column_rows_by_report_ids(self, report_ids: list[int]) -> list[SpeechColumnRow]:
        statement = (
            select(Speech.id, Speech.report_id, Speech.speaker, Speech.transcript, Speech.column_start, Speech.column_note, Speech.column_suggested)
            .where(col(Speech.report_id).in_(report_ids))
            .order_by(Speech.report_id, Speech.ordinal)
        )
        return [SpeechColumnRow(*row) for row in self.session.exec(statement).all()]

    def get_text_rows(self) -> Iterable[SpeechTextRow]:
        statement = (
            select(Speech.id, Speech.report_id, Speech.speaker, Speech.transcript)
            .order_by(Speech.id)
            .execution_options(yield_per=_STREAM_BATCH)
        )
        return (SpeechTextRow(*row) for row in self.session.exec(statement))

    def get_transcript_rows_by_transcript_regex(self, pattern: str) -> list[SpeechTranscriptRow]:
        statement = select(Speech.id, Speech.transcript).where(col(Speech.transcript).regexp_match(pattern)).order_by(Speech.id)
        return [SpeechTranscriptRow(*row) for row in self.session.exec(statement).all()]

    def get_label_rows_by_speaker_regex(self, pattern: str) -> list[SpeechLabelRow]:
        statement = select(Speech.id, Speech.speaker).where(col(Speech.speaker).regexp_match(pattern)).order_by(Speech.id)
        return [SpeechLabelRow(*row) for row in self.session.exec(statement).all()]

    def set_speakers_bulk_by_speaker(self, text_changes: list[TextChange]) -> int:
        if not text_changes:
            return 0

        # NOTE: a row whose label is no longer the before text is left alone and not counted.
        update_result = self.session.execute(
            text(
                "UPDATE speech SET speaker = v.after "
                "FROM UNNEST(CAST(:ids AS integer[]), CAST(:befores AS text[]), CAST(:afters AS text[])) AS v(id, before, after) "
                "WHERE speech.id = v.id AND speech.speaker = v.before"
            ),
            {
                "ids": [text_change.id for text_change in text_changes],
                "befores": [text_change.before for text_change in text_changes],
                "afters": [text_change.after for text_change in text_changes],
            },
        )

        return update_result.rowcount

    def set_transcripts_bulk_by_transcript(self, text_changes: list[TextChange]) -> int:
        if not text_changes:
            return 0

        # NOTE: a row whose transcript is no longer the before text is left alone and not counted.
        update_result = self.session.execute(
            text(
                "UPDATE speech SET transcript = v.after "
                "FROM UNNEST(CAST(:ids AS integer[]), CAST(:befores AS text[]), CAST(:afters AS text[])) AS v(id, before, after) "
                "WHERE speech.id = v.id AND speech.transcript = v.before"
            ),
            {
                "ids": [text_change.id for text_change in text_changes],
                "befores": [text_change.before for text_change in text_changes],
                "afters": [text_change.after for text_change in text_changes],
            },
        )

        return update_result.rowcount

    def get_speaker_id_rows_by_ids_for_update(self, speech_ids: list[int]) -> list[SpeechSpeakerIdRow]:
        statement = select(Speech.id, Speech.speaker_id).where(col(Speech.id).in_(speech_ids)).with_for_update()
        return [SpeechSpeakerIdRow(*row) for row in self.session.exec(statement).all()]

    def get_parliament_rows_by_speaker_not_null_and_parliament_number(self, parliament_number: int) -> list[SpeechParliamentRow]:
        statement = (
            select(Speech.id, Speech.speaker, Report.report_type, Report.parliament_number)
            .join(Report)
            .where(Speech.speaker.is_not(None))
            .where(Report.parliament_number == parliament_number)
        )
        return [SpeechParliamentRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_report_ids(self, report_ids: list[int]) -> int:
        statement = delete(Speech).where(col(Speech.report_id).in_(report_ids))

        return self.session.exec(statement).rowcount

    def set_speaker_ids_bulk(self, speech_id_to_speaker_id: dict[int, Optional[int]]) -> None:
        if not speech_id_to_speaker_id:
            return

        self.session.execute(
            text(
                "UPDATE speech SET speaker_id = v.speaker_id "
                "FROM UNNEST(:ids, CAST(:speaker_ids AS integer[])) AS v(id, speaker_id) "
                "WHERE speech.id = v.id"
            ),
            {"ids": list(speech_id_to_speaker_id.keys()), "speaker_ids": list(speech_id_to_speaker_id.values())},
        )

    def set_column_starts_bulk(self, speech_id_to_column_start: dict[int, Optional[int]]) -> int:
        if not speech_id_to_column_start:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE speech SET column_start = v.column_start "
                "FROM UNNEST(CAST(:ids AS integer[]), CAST(:column_starts AS integer[])) AS v(id, column_start) "
                "WHERE speech.id = v.id"
            ),
            {"ids": list(speech_id_to_column_start.keys()), "column_starts": list(speech_id_to_column_start.values())},
        )

        return update_result.rowcount

    def set_column_notes_bulk(self, speech_column_notes: list[SpeechColumnNote]) -> int:
        if not speech_column_notes:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE speech SET column_note = v.column_note, column_suggested = v.column_suggested "
                "FROM UNNEST(CAST(:ids AS integer[]), CAST(:column_notes AS columnnote[]), CAST(:column_suggesteds AS integer[])) "
                "AS v(id, column_note, column_suggested) "
                "WHERE speech.id = v.id"
            ),
            {
                "ids": [speech_column_note.id for speech_column_note in speech_column_notes],
                "column_notes": [speech_column_note.column_note for speech_column_note in speech_column_notes],
                "column_suggesteds": [speech_column_note.column_suggested for speech_column_note in speech_column_notes],
            },
        )

        return update_result.rowcount

    def get_vacuum_count(self) -> int:
        statement = text("SELECT vacuum_count FROM pg_stat_user_tables WHERE relid = 'speech'::regclass")
        return self.session.execute(statement).scalar_one()

    # NOTE: the commit hands the autocommit connection back, so the session's next statement runs in a transaction
    def vacuum_analyze(self) -> None:
        statement = text("VACUUM (ANALYZE) speech")
        self.session.connection(execution_options={"isolation_level": "AUTOCOMMIT"}).execute(statement)
        self.session.commit()
