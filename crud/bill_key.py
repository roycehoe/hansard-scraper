from dataclasses import dataclass

from sqlmodel import Session, col, delete, select

from database.bill_key import BillKey


@dataclass(frozen=True)
class BillKeyRow:
    id: int
    bill_key: str
    act_count: int
    bill_id: int


class CRUDBillKey:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, bill_keys: list[BillKey]) -> None:
        self.session.add_all(bill_keys)
        self.session.flush()

    def get_rows(self) -> list[BillKeyRow]:
        statement = select(
            BillKey.id, BillKey.bill_key, BillKey.act_count, BillKey.bill_id
        ).order_by(BillKey.bill_id)
        return [BillKeyRow(*row) for row in self.session.exec(statement).all()]

    def delete_by_bill_ids(self, bill_ids: list[int]) -> int:
        statement = delete(BillKey).where(col(BillKey.bill_id).in_(bill_ids))

        return self.session.exec(statement).rowcount

    def delete_all(self) -> int:
        statement = delete(BillKey)

        return self.session.exec(statement).rowcount
