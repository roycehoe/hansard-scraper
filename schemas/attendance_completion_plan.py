from typing import Optional

from pydantic import BaseModel, ConfigDict


class PlannedAttendance(BaseModel):
    model_config = ConfigDict(frozen=True)

    speaker_name: Optional[str]
    is_present: Optional[bool]
    location_name: Optional[str]
    speaker_id: Optional[int]


class SittingAttendanceCompletion(BaseModel):
    model_config = ConfigDict(frozen=True)

    sitting_id: int
    sitting_date: str
    markdown_md5: str
    stored_row_count: int
    built_row_count: int
    rows_to_insert: list[PlannedAttendance]


class AttendanceCompletionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    sittings: list[SittingAttendanceCompletion]
