from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import MinutesFileFormat, MinutesIndexSource, MinutesStatus


class PlannedMinutesIndexCapture(BaseModel):
    model_config = ConfigDict(frozen=True)

    file: str
    original_url: str
    archive_timestamp: Optional[str]
    capture_url: str
    row_count: int


class PlannedMinutesRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    sitting_date: date
    status: MinutesStatus
    is_new_row: bool
    expected_status: Optional[MinutesStatus]
    index_source: Optional[MinutesIndexSource]
    capture_url: Optional[str]
    printed_label: Optional[str]
    printed_parliament: Optional[str]
    file_url: Optional[str]
    file_format: Optional[MinutesFileFormat]


class MinutesIndexPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    captures: list[PlannedMinutesIndexCapture]
    rows: list[PlannedMinutesRow]
    duplicate_count: int
    conflicting_address_count: int
    stored_row_count: int
