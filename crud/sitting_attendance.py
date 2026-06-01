from sqlmodel import Session, select

from database.sitting_attendance import SittingAttendance


class CRUDSittingAttendance:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: SittingAttendance) -> None:
        self.session.add(record)
        self.session.commit()

    def get_sitting_ids_with_attendance(self) -> set[int]:
        rows = self.session.exec(select(SittingAttendance.sitting_id).distinct()).all()
        return {r for r in rows if r is not None}

    def get_unresolved_ids(self) -> list[int]:
        return list(self.session.exec(
            select(SittingAttendance.id).where(SittingAttendance.mp_id == None)  # noqa: E711
        ).all())

    def get_by_ids(self, ids: list[int]) -> list[SittingAttendance]:
        return list(self.session.exec(
            select(SittingAttendance).where(SittingAttendance.id.in_(ids))
        ).all())

    def mark_mp_id(self, record: SittingAttendance, mp_id: int) -> None:
        record.mp_id = mp_id
        self.session.add(record)
