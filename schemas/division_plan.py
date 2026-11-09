from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import DivisionCountSource, DivisionListStatus, UnreadDivisionReason


class PlannedDivision(BaseModel):
    model_config = ConfigDict(frozen=True)

    sprs_report_id: str
    sitting_date: date
    parliament_number: int
    report_division_number: int
    speech_ordinal: int
    count_source: DivisionCountSource
    printed_counts: str
    ayes: Optional[int]
    noes: Optional[int]
    abstentions: Optional[int]
    absent: Optional[int]
    paired: Optional[int]
    list_status: DivisionListStatus
    printed_list: Optional[str]


class PlannedUnreadRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: int
    sprs_report_id: str
    speech_ordinal: int
    reason: UnreadDivisionReason
    printed_text: str


class DivisionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_ids: list[int]
    sprs_report_ids: list[str]
    divisions: list[PlannedDivision]
    unread_rows: list[PlannedUnreadRow]
