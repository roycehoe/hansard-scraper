from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import text
from sqlmodel import Session, col, delete, select

from database.report import Report
from database.speech import Speech

_STREAM_BATCH = 10_000


class CRUDSpeech:
    def __init__(self, session: Session):
        self.session = session

    def create(self, speech: Speech) -> None:
        self.session.add(speech)
        self.session.commit()

    def create_many(self, speeches: list[Speech]) -> None:
        self.session.add_all(speeches)
        self.session.commit()

    def get_report_ids_with_speeches(self) -> set[int]:
        statement = select(Speech.report_id).distinct()
        return set(self.session.exec(statement).all()) - {None}

    def get_speakers_with_report_type(self) -> list[tuple[str, str, int]]:
        statement = (
            select(Speech.speaker, Report.report_type, Report.parliament_number)
            .join(Report, Report.id == Speech.report_id)
            .where(Speech.speaker.is_not(None))
        )
        return list(self.session.exec(statement).all())

    def get_unresolved_speaker_info(self) -> Iterable[tuple[int, Optional[str], int, datetime]]:
        statement = (
            select(Speech.id, Speech.speaker, Report.parliament_number, Report.sitting_date)
            .join(Report)
            .where(col(Speech.speaker_id).is_(None))
            .execution_options(yield_per=_STREAM_BATCH)
        )
        return self.session.exec(statement)

    def get_report_ids_with_unlinked_speaker(self, pattern: str) -> list[int]:
        statement = (
            select(Speech.report_id)
            .distinct()
            .where(col(Speech.speaker_id).is_(None))
            .where(Speech.speaker.regexp_match(pattern, flags="i"))
        )
        return list(self.session.exec(statement).all())

    def get_rows_by_report_ids(
        self, report_ids: list[int]
    ) -> list[tuple[int, int, Optional[str], str, int, Optional[int]]]:
        statement = (
            select(Speech.id, Speech.ordinal, Speech.speaker, Speech.transcript, Speech.report_id, Speech.speaker_id)
            .where(col(Speech.report_id).in_(report_ids))
            .order_by(Speech.report_id, Speech.ordinal)
        )
        return list(self.session.exec(statement).all())

    def get_speaker_info_by_ids(self, speech_ids: list[int]) -> list[tuple[int, str, int, object]]:
        statement = (
            select(Speech.id, Speech.speaker, Report.parliament_number, Report.sitting_date)
            .join(Report)
            .where(Speech.id.in_(speech_ids))
        )
        return list(self.session.exec(statement).all())

    def get_speaker_info_for_parliament(self, parliament_number: int) -> list[tuple[int, str, str, int]]:
        statement = (
            select(Speech.id, Speech.speaker, Report.report_type, Report.parliament_number)
            .join(Report)
            .where(Speech.speaker.is_not(None))
            .where(Report.parliament_number == parliament_number)
        )
        return list(self.session.exec(statement).all())

    def delete_by_report_id(self, report_id: int) -> int:
        statement = delete(Speech).where(Speech.report_id == report_id)
        delete_result = self.session.exec(statement)
        self.session.commit()
        return delete_result.rowcount

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
