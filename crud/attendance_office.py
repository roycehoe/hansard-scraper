from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlmodel import Session, col, delete, func, select

from database.attendance import Attendance
from database.attendance_office import AttendanceOffice
from database.sitting import Sitting
from enums import AttendanceOfficeSource, OfficeClass

_SITTING_DATE_SQL_FORMAT = "DD-MM-YYYY"


@dataclass(frozen=True)
class AttendanceOfficeSittingRow:
    id: int
    sitting_id: int
    sitting_date: str
    speaker_id: Optional[int]
    office_printed: str
    office_class: OfficeClass
    entry_line_printed: str
    source: AttendanceOfficeSource


class CRUDAttendanceOffice:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, attendance_offices: list[AttendanceOffice]) -> None:
        self.session.add_all(attendance_offices)
        self.session.flush()

    def get_sitting_rows_by_sitting_ids(
        self, sitting_ids: list[int]
    ) -> list[AttendanceOfficeSittingRow]:
        statement = (
            select(
                AttendanceOffice.id,
                Attendance.sitting_id,
                Sitting.sitting_date,
                Attendance.speaker_id,
                AttendanceOffice.office_printed,
                AttendanceOffice.office_class,
                AttendanceOffice.entry_line_printed,
                AttendanceOffice.source,
            )
            .join(Attendance, col(Attendance.id) == AttendanceOffice.attendance_id)
            .join(Sitting, col(Sitting.id) == Attendance.sitting_id)
            .where(col(Attendance.sitting_id).in_(sitting_ids))
            .order_by(AttendanceOffice.id)
        )
        return [
            AttendanceOfficeSittingRow(*row) for row in self.session.exec(statement).all()
        ]

    def get_sitting_rows(self) -> list[AttendanceOfficeSittingRow]:
        statement = (
            select(
                AttendanceOffice.id,
                Attendance.sitting_id,
                Sitting.sitting_date,
                Attendance.speaker_id,
                AttendanceOffice.office_printed,
                AttendanceOffice.office_class,
                AttendanceOffice.entry_line_printed,
                AttendanceOffice.source,
            )
            .join(Attendance, col(Attendance.id) == AttendanceOffice.attendance_id)
            .join(Sitting, col(Sitting.id) == Attendance.sitting_id)
            .order_by(AttendanceOffice.id)
        )
        return [
            AttendanceOfficeSittingRow(*row)
            for row in self.session.exec(statement).all()
        ]

    def get_max_sitting_date_by_sitting_ids_not_in(
        self, sitting_ids: list[int]
    ) -> Optional[date]:
        statement = (
            select(func.max(func.to_date(Sitting.sitting_date, _SITTING_DATE_SQL_FORMAT)))
            .join(Attendance, col(Attendance.sitting_id) == Sitting.id)
            .join(AttendanceOffice, col(AttendanceOffice.attendance_id) == Attendance.id)
            .where(col(Sitting.id).not_in(sitting_ids))
        )
        return self.session.exec(statement).one()

    def get_distinct_office_printed(self) -> list[str]:
        statement = (
            select(AttendanceOffice.office_printed)
            .distinct()
            .order_by(AttendanceOffice.office_printed)
        )
        return list(self.session.exec(statement).all())

    def get_distinct_office_printed_by_sitting_ids(
        self, sitting_ids: list[int]
    ) -> list[str]:
        statement = (
            select(AttendanceOffice.office_printed)
            .distinct()
            .join(Attendance, col(Attendance.id) == AttendanceOffice.attendance_id)
            .where(col(Attendance.sitting_id).in_(sitting_ids))
            .order_by(AttendanceOffice.office_printed)
        )
        return list(self.session.exec(statement).all())

    def delete_by_attendance_ids(self, attendance_ids: list[int]) -> int:
        statement = delete(AttendanceOffice).where(
            col(AttendanceOffice.attendance_id).in_(attendance_ids)
        )

        return self.session.exec(statement).rowcount

    def delete_by_sitting_ids(self, sitting_ids: list[int]) -> int:
        attendance_ids = select(Attendance.id).where(
            col(Attendance.sitting_id).in_(sitting_ids)
        )
        statement = delete(AttendanceOffice).where(
            col(AttendanceOffice.attendance_id).in_(attendance_ids)
        )

        return self.session.exec(statement).rowcount
