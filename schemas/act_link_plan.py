from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import ActHistoryDefect, ActHistoryEntryKind, BillLinkSource


class PlannedBill(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    title_key: str
    first_sitting_date: datetime
    last_sitting_date: datetime
    is_passed: bool
    report_ids: list[int]


class SkippedReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: int
    title: str


class PlannedActHistoryEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

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
    defects: list[ActHistoryDefect]
    bill_index: Optional[int]
    bill_link_source: Optional[BillLinkSource]


class PlannedAct(BaseModel):
    model_config = ConfigDict(frozen=True)

    sso_code: str
    title: str
    entries: list[PlannedActHistoryEntry]


class UnparsedEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    sso_code: str
    message: str


class ActLinkPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    bills: list[PlannedBill]
    skipped_reports: list[SkippedReport]
    acts: list[PlannedAct]
    unfetched_sso_codes: list[str]
    unparsed_entries: list[UnparsedEntry]
