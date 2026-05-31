from sqlmodel import Session

from database.sitting_attendance import SittingAttendance


class CRUDSittingAttendance:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: SittingAttendance) -> None:
        self.session.add(record)
        self.session.commit()
