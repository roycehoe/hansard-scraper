from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from enums import (
    ActHistoryEntryKind,
    ActNumberSource,
    BillClass,
    BillLinkSource,
    BillNumberSource,
)


@dataclass(frozen=True)
class BillUpdate:
    id: int
    title: str
    title_key: str
    first_sitting_date: datetime
    last_sitting_date: datetime
    is_passed: bool
    bill_number: Optional[str]
    bill_number_source: Optional[BillNumberSource]
    bill_class: Optional[BillClass]
    act_number: Optional[str]
    act_number_source: Optional[ActNumberSource]


@dataclass(frozen=True)
class ActUpdate:
    id: int
    title: str


@dataclass(frozen=True)
class ActHistoryEntryUpdate:
    id: int
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
