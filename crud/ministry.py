from sqlmodel import Session, col, delete, select

from database.ministry import Ministry


class CRUDMinistry:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, ministries: list[Ministry]) -> None:
        self.session.add_all(ministries)
        self.session.flush()

    def get_all(self) -> list[Ministry]:
        statement = select(Ministry).order_by(Ministry.id)
        return list(self.session.exec(statement).all())

    def delete_by_ids(self, ministry_ids: list[int]) -> int:
        statement = delete(Ministry).where(col(Ministry.id).in_(ministry_ids))

        return self.session.exec(statement).rowcount
