from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import text
from sqlmodel import Session, col, delete, func, select

from database.attendance import Attendance
from database.sitting import Sitting


@dataclass(frozen=True)
class AttendanceSpeakerRow:
    id: int
    speaker_name: Optional[str]
    parlement_no: Optional[int]
    volume_no: Optional[int]


@dataclass(frozen=True)
class AttendancePresenceRow:
    sitting_id: int
    speaker_id: int
    is_present: Optional[bool]


@dataclass(frozen=True)
class AttendanceLocationRow:
    id: int
    speaker_name: Optional[str]
    location_name: str
    sitting_date: Optional[str]
    parlement_no: Optional[int]
    volume_no: Optional[int]


@dataclass(frozen=True)
class AttendanceSittingCount:
    sitting_id: int
    row_count: int


@dataclass(frozen=True)
class AttendanceTextRow:
    id: int
    speaker_name: Optional[str]
    location_name: Optional[str]


_STREAM_BATCH = 10_000


class CRUDAttendance:
    def __init__(self, session: Session):
        self.session = session

    def create_many(self, attendances: list[Attendance]) -> None:
        self.session.add_all(attendances)
        self.session.commit()

    def add_many(self, attendances: list[Attendance]) -> None:
        self.session.add_all(attendances)
        self.session.flush()

    def get_all(self) -> list[Attendance]:
        statement = select(Attendance).order_by(col(Attendance.sitting_id), Attendance.id)
        return list(self.session.exec(statement).all())

    def get_text_rows(self) -> Iterable[AttendanceTextRow]:
        statement = (
            select(Attendance.id, Attendance.speaker_name, Attendance.location_name)
            .order_by(Attendance.id)
            .execution_options(yield_per=_STREAM_BATCH)
        )
        return (AttendanceTextRow(*row) for row in self.session.exec(statement))

    def get_by_ids(self, attendance_ids: list[int]) -> list[Attendance]:
        statement = select(Attendance).where(col(Attendance.id).in_(attendance_ids))
        return list(self.session.exec(statement).all())

    def get_by_ids_for_update(self, attendance_ids: list[int]) -> list[Attendance]:
        statement = select(Attendance).where(col(Attendance.id).in_(attendance_ids)).with_for_update()
        return list(self.session.exec(statement).all())

    def get_by_sitting_ids(self, sitting_ids: list[int]) -> list[Attendance]:
        statement = select(Attendance).where(col(Attendance.sitting_id).in_(sitting_ids))
        return list(self.session.exec(statement).all())

    def get_count_by_sitting_ids_and_speaker_id_not_null(self, sitting_ids: list[int]) -> int:
        statement = (
            select(func.count())
            .select_from(Attendance)
            .where(col(Attendance.sitting_id).in_(sitting_ids))
            .where(col(Attendance.speaker_id).is_not(None))
        )
        return self.session.exec(statement).one()

    def get_distinct_sitting_ids(self) -> set[int]:
        statement = select(Attendance.sitting_id).distinct()
        return set(self.session.exec(statement).all())

    def get_presence_rows_by_speaker_id_not_null(self) -> list[AttendancePresenceRow]:
        statement = (
            select(Attendance.sitting_id, Attendance.speaker_id, Attendance.is_present)
            .where(col(Attendance.speaker_id).is_not(None))
        )
        return [AttendancePresenceRow(*row) for row in self.session.exec(statement).all()]

    def get_sitting_counts(self) -> list[AttendanceSittingCount]:
        statement = select(Attendance.sitting_id, func.count()).group_by(col(Attendance.sitting_id))
        return [AttendanceSittingCount(*row) for row in self.session.exec(statement).all()]

    def get_speaker_rows_by_speaker_id_null(self) -> list[AttendanceSpeakerRow]:
        statement = (
            select(Attendance.id, Attendance.speaker_name, Sitting.parlement_no, Sitting.volume_no)
            .join(Sitting)
            .where(col(Attendance.speaker_id).is_(None))
        )
        return [AttendanceSpeakerRow(*row) for row in self.session.exec(statement).all()]

    def get_speaker_rows_by_sitting_ids_and_speaker_id_null(self, sitting_ids: list[int]) -> list[AttendanceSpeakerRow]:
        statement = (
            select(Attendance.id, Attendance.speaker_name, Sitting.parlement_no, Sitting.volume_no)
            .join(Sitting)
            .where(col(Attendance.speaker_id).is_(None))
            .where(col(Attendance.sitting_id).in_(sitting_ids))
        )
        return [AttendanceSpeakerRow(*row) for row in self.session.exec(statement).all()]

    def get_location_rows_by_location_name_not_null(self) -> list[AttendanceLocationRow]:
        statement = (
            select(Attendance.id, Attendance.speaker_name, Attendance.location_name, Sitting.sitting_date, Sitting.parlement_no, Sitting.volume_no)
            .join(Sitting)
            .where(col(Attendance.location_name).is_not(None))
        )
        return [AttendanceLocationRow(*row) for row in self.session.exec(statement).all()]

    def update_many(self, attendances: list[Attendance]) -> None:
        self.session.add_all(attendances)
        self.session.flush()

    def delete_by_ids(self, attendance_ids: list[int]) -> int:
        statement = delete(Attendance).where(col(Attendance.id).in_(attendance_ids))

        return self.session.exec(statement).rowcount

    def set_location_names_bulk(self, attendance_id_to_location_name: dict[int, str]) -> int:
        if not attendance_id_to_location_name:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE attendance SET location_name = v.location_name "
                "FROM UNNEST(:ids, :location_names) AS v(id, location_name) "
                "WHERE attendance.id = v.id"
            ),
            {"ids": list(attendance_id_to_location_name.keys()), "location_names": list(attendance_id_to_location_name.values())},
        )

        return update_result.rowcount

    def set_speaker_names_bulk(self, attendance_id_to_speaker_name: dict[int, str]) -> int:
        if not attendance_id_to_speaker_name:
            return 0

        update_result = self.session.execute(
            text(
                "UPDATE attendance SET speaker_name = v.speaker_name "
                "FROM UNNEST(:ids, :speaker_names) AS v(id, speaker_name) "
                "WHERE attendance.id = v.id"
            ),
            {"ids": list(attendance_id_to_speaker_name.keys()), "speaker_names": list(attendance_id_to_speaker_name.values())},
        )

        return update_result.rowcount

    def set_speaker_ids_bulk(self, attendance_id_to_speaker_id: dict[int, int]) -> None:
        if not attendance_id_to_speaker_id:
            return

        self.session.execute(
            text(
                "UPDATE attendance SET speaker_id = v.speaker_id "
                "FROM UNNEST(:ids, :speaker_ids) AS v(id, speaker_id) "
                "WHERE attendance.id = v.id"
            ),
            {"ids": list(attendance_id_to_speaker_id.keys()), "speaker_ids": list(attendance_id_to_speaker_id.values())},
        )

    def get_vacuum_count(self) -> int:
        statement = text("SELECT vacuum_count FROM pg_stat_user_tables WHERE relid = 'attendance'::regclass")
        return self.session.execute(statement).scalar_one()

    # NOTE: the commit hands the autocommit connection back, so the session's next statement runs in a transaction
    def vacuum_analyze(self) -> None:
        statement = text("VACUUM (ANALYZE) attendance")
        self.session.connection(execution_options={"isolation_level": "AUTOCOMMIT"}).execute(statement)
        self.session.commit()
