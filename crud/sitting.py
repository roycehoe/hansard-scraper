from sqlmodel import Session, select

from database.sitting import Sitting


class CRUDSitting:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sitting: Sitting) -> None:
        self.session.add(sitting)
        self.session.commit()

    def get_all(self) -> list[Sitting]:
        return list(self.session.exec(select(Sitting)).all())
