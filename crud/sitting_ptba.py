from sqlmodel import Session

from database.sitting_ptba import SittingPtba


class CRUDSittingPtba:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: SittingPtba) -> None:
        self.session.add(record)
        self.session.commit()
