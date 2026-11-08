from dataclasses import dataclass
from datetime import date

from sqlmodel import Session, col, func, select

from database.acts_supplement import ActsSupplementEntry


@dataclass(frozen=True)
class ActsSupplementEntryRow:
    id: int
    printed_title: str
    printed_number: str
    link: str
    act_number: str
    publication_date: date
    capture_id: int


class CRUDActsSupplementEntry:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, entries: list[ActsSupplementEntry]) -> None:
        self.session.add_all(entries)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(ActsSupplementEntry)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[ActsSupplementEntryRow]:
        statement = select(
            ActsSupplementEntry.id,
            ActsSupplementEntry.printed_title,
            ActsSupplementEntry.printed_number,
            ActsSupplementEntry.link,
            ActsSupplementEntry.act_number,
            ActsSupplementEntry.publication_date,
            ActsSupplementEntry.capture_id,
        ).order_by(col(ActsSupplementEntry.id))
        return [
            ActsSupplementEntryRow(*row) for row in self.session.exec(statement).all()
        ]
