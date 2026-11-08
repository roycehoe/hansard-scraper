from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, col, func, select

from database.bills_supplement import BillsSupplementEntry


@dataclass(frozen=True)
class BillsSupplementEntryRow:
    id: int
    printed_title: str
    printed_number: str
    link: str
    bill_number: str
    publication_date: date
    capture_id: int


class CRUDBillsSupplementEntry:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, entries: list[BillsSupplementEntry]) -> None:
        self.session.add_all(entries)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(BillsSupplementEntry)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[BillsSupplementEntryRow]:
        statement = select(
            BillsSupplementEntry.id,
            BillsSupplementEntry.printed_title,
            BillsSupplementEntry.printed_number,
            BillsSupplementEntry.link,
            BillsSupplementEntry.bill_number,
            BillsSupplementEntry.publication_date,
            BillsSupplementEntry.capture_id,
        ).order_by(col(BillsSupplementEntry.id))
        return [
            BillsSupplementEntryRow(*row) for row in self.session.exec(statement).all()
        ]
