from sqlmodel import Session

from database.sitting_a2b import SittingA2b


class CRUDSittingA2b:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: SittingA2b) -> None:
        self.session.add(record)
        self.session.commit()
