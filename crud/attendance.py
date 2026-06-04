from sqlalchemy import text
from sqlmodel import Session, select

from database.attendance import Attendance


class CRUDAttendance:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: Attendance) -> None:
        self.session.add(record)
        self.session.commit()

    def get_sitting_ids_with_attendance(self) -> set[int]:
        rows = self.session.exec(select(Attendance.sitting_id).distinct()).all()
        return {r for r in rows if r is not None}

    def get_unresolved_ids(self) -> list[int]:
        return list(self.session.exec(
            select(Attendance.id).where(Attendance.speaker_id == None)  # noqa: E711
        ).all())

    def get_by_ids(self, ids: list[int]) -> list[Attendance]:
        return list(self.session.exec(
            select(Attendance).where(Attendance.id.in_(ids))
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
