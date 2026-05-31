from sqlmodel import Session, select

from database.sitting import Sitting


class CRUDSitting:
    def __init__(self, session: Session):
        self.session = session

    def create(self, sitting: Sitting) -> None:
        self.session.add(sitting)
        self.session.commit()

    def exists_by_sitting_date(self, sitting_date: str) -> bool:
        return self.session.exec(
            select(Sitting).where(Sitting.sitting_date == sitting_date)
        ).first() is not None

    def get_all(self) -> list[Sitting]:
        return list(self.session.exec(select(Sitting)).all())
