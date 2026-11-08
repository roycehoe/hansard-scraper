from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PlannedRepealedActsCapture(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_name: str
    original_url: str
    archive_timestamp: str
    capture_url: str
    row_count: int


class PlannedRepealedActEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    printed_title: str
    printed_chapter: Optional[str]
    link: str
    sso_code: str
    enactment_year: Optional[int]
    repeal_date: date
    last_version_date: date
    capture_url: str


class RepealedActsPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    captures: list[PlannedRepealedActsCapture]
    entries: list[PlannedRepealedActEntry]
    duplicate_count: int
