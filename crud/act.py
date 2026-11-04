from dataclasses import dataclass

from sqlalchemy import update
from sqlmodel import Session, col, delete, func, select

from database.act import Act
from utils.act_link_update import ActUpdate


@dataclass(frozen=True)
class ActRow:
    id: int
    sso_code: str
    title: str


class CRUDAct:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, acts: list[Act]) -> None:
        self.session.add_all(acts)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(Act)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[ActRow]:
        statement = select(Act.id, Act.sso_code, Act.title).order_by(col(Act.id))
        return [ActRow(*row) for row in self.session.exec(statement).all()]

    def update_many(self, act_updates: list[ActUpdate]) -> None:
        if not act_updates:
            return

        self.session.execute(
            update(Act),
            [
                {"id": act_update.id, "title": act_update.title}
                for act_update in act_updates
            ],
        )

    def delete_by_ids(self, act_ids: list[int]) -> None:
        if not act_ids:
            return

        statement = delete(Act).where(col(Act.id).in_(act_ids))
        self.session.execute(statement)
