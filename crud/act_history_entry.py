from sqlmodel import Session, col, func, select

from database.act import ActHistoryEntry


class CRUDActHistoryEntry:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, act_history_entries: list[ActHistoryEntry]) -> None:
        self.session.add_all(act_history_entries)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(ActHistoryEntry)
        return self.session.exec(statement).one()

    def get_count_by_bill_id_not_null(self) -> int:
        statement = (
            select(func.count())
            .select_from(ActHistoryEntry)
            .where(col(ActHistoryEntry.bill_id).is_not(None))
        )
        return self.session.exec(statement).one()
