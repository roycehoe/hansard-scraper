from typing import Optional

from sqlalchemy import text
from sqlmodel import Session, select

from database.attendance import Attendance
from database.sitting import Sitting


class CRUDAttendance:
    def __init__(self, session: Session):
        self.session = session

    def create(self, attendance: Attendance) -> None:
        self.session.add(attendance)
        self.session.commit()

    def create_many(self, attendances: list[Attendance]) -> None:
        self.session.add_all(attendances)
        self.session.commit()

    def get_sitting_ids_with_attendance(self) -> set[int]:
        sitting_ids = self.session.exec(select(Attendance.sitting_id).distinct()).all()
        return {sitting_id for sitting_id in sitting_ids if sitting_id is not None}

    def get_unresolved_speaker_info(
        self,
    ) -> list[tuple[int, Optional[str], Optional[int], Optional[int]]]:
        """(id, speaker_name, sitting.parlement_no, sitting.volume_no) for every row without a speaker_id."""
        return list(self.session.exec(
            select(Attendance.id, Attendance.speaker_name, Sitting.parlement_no, Sitting.volume_no)
            .join(Sitting)
            .where(Attendance.speaker_id == None)  # noqa: E711
        ).all())

    def set_speaker_ids_bulk(self, updates: dict[int, int]) -> None:
        if not updates:
            return
        self.session.execute(
            text(
                "UPDATE attendance SET speaker_id = v.speaker_id "
                "FROM UNNEST(:ids, :speaker_ids) AS v(id, speaker_id) "
                "WHERE attendance.id = v.id"
            ),
            {"ids": list(updates.keys()), "speaker_ids": list(updates.values())},
        )
