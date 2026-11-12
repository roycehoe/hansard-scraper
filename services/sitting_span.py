from dataclasses import dataclass
from datetime import date

from crud.attendance import AttendanceSittingDateRow
from utils.sitting_dates import parse_sitting_date


@dataclass(frozen=True)
class SittingSpanRecord:
    first_sitting_date: date
    last_sitting_date: date
    sitting_count: int
    speaker_id: int


def build_sitting_span_records(
    attendance_sitting_date_rows: list[AttendanceSittingDateRow],
) -> list[SittingSpanRecord]:
    speaker_id_to_sitting_dates: dict[int, set[date]] = {}
    for attendance_sitting_date_row in attendance_sitting_date_rows:
        speaker_id_to_sitting_dates.setdefault(
            attendance_sitting_date_row.speaker_id, set()
        ).add(parse_sitting_date(attendance_sitting_date_row.sitting_date).date())

    return [
        SittingSpanRecord(
            min(sitting_dates), max(sitting_dates), len(sitting_dates), speaker_id
        )
        for speaker_id, sitting_dates in sorted(speaker_id_to_sitting_dates.items())
    ]
