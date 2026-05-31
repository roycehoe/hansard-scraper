from sqlmodel import Session

from database.sitting_section import SittingSection


class CRUDSittingSection:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: SittingSection) -> None:
        self.session.add(record)
        self.session.commit()
