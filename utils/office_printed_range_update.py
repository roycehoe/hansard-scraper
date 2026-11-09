from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class OfficePrintedRangeUpdate:
    id: int
    last_attendance_office_id: int
    last_sitting_date: datetime
    sitting_count: int
    built_at: datetime
