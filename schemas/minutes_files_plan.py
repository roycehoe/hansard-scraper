from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import MinutesFileFormat, MinutesIndexSource, MinutesStatus


class PlannedMinutesFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    sitting_date: date
    file_url: Optional[str]
    is_new_row: bool
    expected_status: Optional[MinutesStatus]
    status: MinutesStatus
    status_note: Optional[str]
    index_source: Optional[MinutesIndexSource]
    file_name: Optional[str]
    file_format: Optional[MinutesFileFormat]
    archive_timestamp: Optional[str]
    sha256: Optional[str]
    size_bytes: Optional[int]
    fetched_at: Optional[datetime]
    extracted_character_count: Optional[int]
    extracted_text_sha256: Optional[str]


class FlaggedMinutesFile(BaseModel):
    model_config = ConfigDict(frozen=True)

    file_url: str
    reason: str


class MinutesFilesPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    files: list[PlannedMinutesFile]
    flagged: list[FlaggedMinutesFile]
    already_stored_count: int
