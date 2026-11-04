from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import update
from sqlmodel import Session, col, delete, func, select

from database.act import ActHistoryEntry
from enums import ActHistoryEntryKind, BillLinkSource
from utils.act_link_update import ActHistoryEntryUpdate


@dataclass(frozen=True)
class ActHistoryEntryRow:
    id: int
    act_id: int
    ordinal: int
    printed_text: str
    printed_law_number: str
    printed_title: str
    printed_bill_number: Optional[str]
    first_reading_date: Optional[date]
    second_reading_date: Optional[date]
    third_reading_date: Optional[date]
    commencement_date: Optional[date]
    kind: ActHistoryEntryKind
    bill_link_source: Optional[BillLinkSource]
    bill_id: Optional[int]


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

    def get_rows(self) -> list[ActHistoryEntryRow]:
        statement = select(
            ActHistoryEntry.id,
            ActHistoryEntry.act_id,
            ActHistoryEntry.ordinal,
            ActHistoryEntry.printed_text,
            ActHistoryEntry.printed_law_number,
            ActHistoryEntry.printed_title,
            ActHistoryEntry.printed_bill_number,
            ActHistoryEntry.first_reading_date,
            ActHistoryEntry.second_reading_date,
            ActHistoryEntry.third_reading_date,
            ActHistoryEntry.commencement_date,
            ActHistoryEntry.kind,
            ActHistoryEntry.bill_link_source,
            ActHistoryEntry.bill_id,
        ).order_by(col(ActHistoryEntry.id))
        return [ActHistoryEntryRow(*row) for row in self.session.exec(statement).all()]

    def update_many(
        self, act_history_entry_updates: list[ActHistoryEntryUpdate]
    ) -> None:
        if not act_history_entry_updates:
            return

        self.session.execute(
            update(ActHistoryEntry),
            [
                {
                    "id": entry_update.id,
                    "printed_text": entry_update.printed_text,
                    "printed_law_number": entry_update.printed_law_number,
                    "printed_title": entry_update.printed_title,
                    "printed_bill_number": entry_update.printed_bill_number,
                    "first_reading_date": entry_update.first_reading_date,
                    "second_reading_date": entry_update.second_reading_date,
                    "third_reading_date": entry_update.third_reading_date,
                    "commencement_date": entry_update.commencement_date,
                    "kind": entry_update.kind,
                    "bill_link_source": entry_update.bill_link_source,
                    "bill_id": entry_update.bill_id,
                }
                for entry_update in act_history_entry_updates
            ],
        )

    def delete_by_ids(self, act_history_entry_ids: list[int]) -> None:
        if not act_history_entry_ids:
            return

        statement = delete(ActHistoryEntry).where(
            col(ActHistoryEntry.id).in_(act_history_entry_ids)
        )
        self.session.execute(statement)
