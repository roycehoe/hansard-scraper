from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import AttendanceCleanupReason


class AttendanceRowKey(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: int
    sitting_id: int
    speaker_name: str
    is_present: bool


class AttendanceRemoval(AttendanceRowKey):
    reason: AttendanceCleanupReason


class AttendanceCorrection(AttendanceRowKey):
    location_name: Optional[str]
    speaker_name_after: str
    location_name_after: Optional[str]
    reason: AttendanceCleanupReason


class AttendanceSpeakerRole(AttendanceRowKey):
    sitting_date: str
    location_name: Optional[str]


class AttendanceCleanup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    removals: list[AttendanceRemoval]
    corrections: list[AttendanceCorrection]
    speaker_roles: list[AttendanceSpeakerRole]
