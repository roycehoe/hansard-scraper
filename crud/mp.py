from sqlmodel import Session, select

from database.mp import Mp


class CRUDMp:
    def __init__(self, session: Session):
        self.session = session

    def create(self, mp: Mp) -> None:
        self.session.add(mp)
        self.session.commit()

    def get_all(self) -> list[Mp]:
        return list(self.session.exec(select(Mp)).all())
