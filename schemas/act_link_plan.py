from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class ActLinkPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    bills: list[PlannedBill]
    skipped_reports: list[SkippedReport]
