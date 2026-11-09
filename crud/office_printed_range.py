from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, update
from sqlmodel import Session, col, delete, select

from database.attendance_office import AttendanceOffice
from database.office_printed_range import OfficePrintedRange
from utils.office_printed_range_update import OfficePrintedRangeUpdate


@dataclass(frozen=True)
class OfficePrintedRangeRow:
    id: int
    speaker_id: int
    office_printed: str
    sitting_count: int
    first_sitting_date: datetime
    last_sitting_date: datetime


class CRUDOfficePrintedRange:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, office_printed_ranges: list[OfficePrintedRange]) -> None:
        self.session.add_all(office_printed_ranges)
        self.session.flush()

    def get_rows_by_speaker_ids(
        self, speaker_ids: list[int]
    ) -> list[OfficePrintedRangeRow]:
        statement = (
            select(
                OfficePrintedRange.id,
                OfficePrintedRange.speaker_id,
                OfficePrintedRange.office_printed,
                OfficePrintedRange.sitting_count,
                OfficePrintedRange.first_sitting_date,
                OfficePrintedRange.last_sitting_date,
            )
            .where(col(OfficePrintedRange.speaker_id).in_(speaker_ids))
            .order_by(
                OfficePrintedRange.speaker_id, OfficePrintedRange.first_sitting_date
            )
        )
        return [
            OfficePrintedRangeRow(*row) for row in self.session.exec(statement).all()
        ]

    def update_many(
        self, office_printed_range_updates: list[OfficePrintedRangeUpdate]
    ) -> None:
        if not office_printed_range_updates:
            return

        self.session.execute(
            update(OfficePrintedRange),
            [
                {
                    "id": office_printed_range_update.id,
                    "last_attendance_office_id": office_printed_range_update.last_attendance_office_id,
                    "last_sitting_date": office_printed_range_update.last_sitting_date,
                    "sitting_count": office_printed_range_update.sitting_count,
                    "built_at": office_printed_range_update.built_at,
                }
                for office_printed_range_update in office_printed_range_updates
            ],
        )

    def delete_by_attendance_ids(self, attendance_ids: list[int]) -> int:
        attendance_office_ids = select(AttendanceOffice.id).where(
            col(AttendanceOffice.attendance_id).in_(attendance_ids)
        )
        statement = delete(OfficePrintedRange).where(
            or_(
                col(OfficePrintedRange.first_attendance_office_id).in_(
                    attendance_office_ids
                ),
                col(OfficePrintedRange.last_attendance_office_id).in_(
                    attendance_office_ids
                ),
            )
        )

        return self.session.exec(statement).rowcount

    def delete_all(self) -> int:
        statement = delete(OfficePrintedRange)

        return self.session.exec(statement).rowcount
