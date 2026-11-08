from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from enums import BillLinkSource, EgazetteSupplementKind


@dataclass(frozen=True)
class EgazetteSupplementUpdate:
    id: int
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


@dataclass(frozen=True)
class EgazetteLinkUpdate:
    id: int
    bill_id: Optional[int]
    bill_link_source: Optional[BillLinkSource]
