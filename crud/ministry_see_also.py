from sqlmodel import Session, delete, select

from database.ministry_see_also import MinistrySeeAlso


class CRUDMinistrySeeAlso:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, ministry_see_alsos: list[MinistrySeeAlso]) -> None:
        self.session.add_all(ministry_see_alsos)
        self.session.flush()

    def get_all(self) -> list[MinistrySeeAlso]:
        statement = select(MinistrySeeAlso).order_by(MinistrySeeAlso.id)
        return list(self.session.exec(statement).all())

    def delete_all(self) -> int:
        statement = delete(MinistrySeeAlso)

        return self.session.exec(statement).rowcount
