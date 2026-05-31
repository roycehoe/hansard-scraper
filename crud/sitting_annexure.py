from sqlmodel import Session

from database.sitting_annexure import SittingAnnexure


class CRUDSittingAnnexure:
    def __init__(self, session: Session):
        self.session = session

    def create(self, record: SittingAnnexure) -> None:
        self.session.add(record)
        self.session.commit()
