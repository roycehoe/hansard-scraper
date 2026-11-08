from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlmodel import Session, col, func, select

from database.repealed_acts import RepealedActEntry


@dataclass(frozen=True)
class RepealedActEntryRow:
    id: int
    printed_title: str
    link: str
    sso_code: str
    enactment_year: Optional[int]
    repeal_date: date
    capture_id: int


class CRUDRepealedActEntry:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, entries: list[RepealedActEntry]) -> None:
        self.session.add_all(entries)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(RepealedActEntry)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[RepealedActEntryRow]:
        statement = select(
            RepealedActEntry.id,
            RepealedActEntry.printed_title,
            RepealedActEntry.link,
            RepealedActEntry.sso_code,
            RepealedActEntry.enactment_year,
            RepealedActEntry.repeal_date,
            RepealedActEntry.capture_id,
        ).order_by(col(RepealedActEntry.id))
        return [RepealedActEntryRow(*row) for row in self.session.exec(statement).all()]
