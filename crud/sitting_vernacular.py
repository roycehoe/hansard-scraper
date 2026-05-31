from sqlmodel import Session

from database.sitting_vernacular import SittingVernacular


class CRUDSittingVernacular:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: SittingVernacular) -> None:
        self.session.add(record)
        self.session.commit()
