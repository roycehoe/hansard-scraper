from sqlmodel import Session, func, select

from database.act import Act


class CRUDAct:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, acts: list[Act]) -> None:
        self.session.add_all(acts)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(Act)
        return self.session.exec(statement).one()
