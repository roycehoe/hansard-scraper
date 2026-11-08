from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PlannedActsSupplementCapture(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_name: str
    original_url: str
    archive_timestamp: str
    capture_url: str
    row_count: int


class PlannedActsSupplementEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    printed_title: str
    printed_number: str
    link: str
    pdf_link: Optional[str]
    pdf_size: Optional[str]
    act_number: str
    publication_date: date
    capture_url: str


class ActsSupplementPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    captures: list[PlannedActsSupplementCapture]
    entries: list[PlannedActsSupplementEntry]
    duplicate_count: int
