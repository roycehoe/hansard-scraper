from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import sqlalchemy
from sqlalchemy import update
from sqlmodel import Session, col, func, select

from database.egazette_supplement import EgazetteSupplement
from enums import BillLinkSource, EgazetteSupplementKind
from utils.egazette_supplement_update import (
    EgazetteLinkUpdate,
    EgazetteSupplementUpdate,
)


@dataclass(frozen=True)
class EgazetteSupplementRow:
    id: int
    url: str
    year: int
    supplement_kind: EgazetteSupplementKind
    number: int
    file_path: str
    size_bytes: int
    sha256: str
    printed_title: str
    printed_bill_number: str
    bill_number: str
    first_reading_date: date
    passing_date: Optional[date]
    printed_act_number: Optional[str]
    fetched_at: datetime
    bill_id: Optional[int]
    bill_link_source: Optional[BillLinkSource]


class CRUDEgazetteSupplement:
    def __init__(self, session: Session):
        self.session = session

    def add_many(self, egazette_supplements: list[EgazetteSupplement]) -> None:
        self.session.add_all(egazette_supplements)
        self.session.flush()

    def get_count(self) -> int:
        statement = select(func.count()).select_from(EgazetteSupplement)
        return self.session.exec(statement).one()

    def get_rows(self) -> list[EgazetteSupplementRow]:
        statement = sqlalchemy.select(
            col(EgazetteSupplement.id),
            col(EgazetteSupplement.url),
            col(EgazetteSupplement.year),
            col(EgazetteSupplement.supplement_kind),
            col(EgazetteSupplement.number),
            col(EgazetteSupplement.file_path),
            col(EgazetteSupplement.size_bytes),
            col(EgazetteSupplement.sha256),
            col(EgazetteSupplement.printed_title),
            col(EgazetteSupplement.printed_bill_number),
            col(EgazetteSupplement.bill_number),
            col(EgazetteSupplement.first_reading_date),
            col(EgazetteSupplement.passing_date),
            col(EgazetteSupplement.printed_act_number),
            col(EgazetteSupplement.fetched_at),
            col(EgazetteSupplement.bill_id),
            col(EgazetteSupplement.bill_link_source),
        ).order_by(col(EgazetteSupplement.id))
        return [
            EgazetteSupplementRow(*row) for row in self.session.execute(statement).all()
        ]

    def update_many(
        self, egazette_supplement_updates: list[EgazetteSupplementUpdate]
    ) -> None:
        if not egazette_supplement_updates:
            return

        self.session.execute(
            update(EgazetteSupplement),
            [
                {
                    "id": egazette_supplement_update.id,
                    "year": egazette_supplement_update.year,
                    "supplement_kind": egazette_supplement_update.supplement_kind,
                    "number": egazette_supplement_update.number,
                    "file_path": egazette_supplement_update.file_path,
                    "size_bytes": egazette_supplement_update.size_bytes,
                    "sha256": egazette_supplement_update.sha256,
                    "printed_title": egazette_supplement_update.printed_title,
                    "printed_bill_number": egazette_supplement_update.printed_bill_number,
                    "bill_number": egazette_supplement_update.bill_number,
                    "first_reading_date": egazette_supplement_update.first_reading_date,
                    "passing_date": egazette_supplement_update.passing_date,
                    "printed_act_number": egazette_supplement_update.printed_act_number,
                    "fetched_at": egazette_supplement_update.fetched_at,
                }
                for egazette_supplement_update in egazette_supplement_updates
            ],
        )

    def set_bill_links_bulk(
        self, egazette_link_updates: list[EgazetteLinkUpdate]
    ) -> None:
        if not egazette_link_updates:
            return

        self.session.execute(
            update(EgazetteSupplement),
            [
                {
                    "id": egazette_link_update.id,
                    "bill_id": egazette_link_update.bill_id,
                    "bill_link_source": egazette_link_update.bill_link_source,
                }
                for egazette_link_update in egazette_link_updates
            ],
        )

    def get_count_by_bill_id_not_null(self) -> int:
        statement = (
            select(func.count())
            .select_from(EgazetteSupplement)
            .where(col(EgazetteSupplement.bill_id).is_not(None))
        )
        return self.session.exec(statement).one()
