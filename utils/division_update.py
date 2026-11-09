from dataclasses import dataclass
from datetime import date
from typing import Optional

from enums import DivisionCountSource, DivisionListStatus


@dataclass(frozen=True)
class DivisionUpdate:
    id: int
    sitting_date: date
    parliament_number: int
    report_division_number: Optional[int]
    speech_ordinal: Optional[int]
    count_source: DivisionCountSource
    printed_counts: str
    ayes: Optional[int]
    noes: Optional[int]
    abstentions: Optional[int]
    absent: Optional[int]
    paired: Optional[int]
    list_status: DivisionListStatus
    printed_list: Optional[str]
