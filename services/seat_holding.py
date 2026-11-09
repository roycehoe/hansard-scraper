import re
from dataclasses import dataclass
from datetime import date

from crud.attendance import AttendanceSeatRow
from utils.sitting_dates import parse_sitting_date

_SEPARATOR_RE = re.compile(r"[\s-]+", re.ASCII)
_DIVISION_SUFFIX_RE = re.compile(r"\s(GRC|SMC)$", re.IGNORECASE | re.ASCII)
_NON_DIVISION_LOCATION_NAMES = frozenset(
    {"Nominated Member", "Nominated", "Non-Constituency Member", "ex-officio", "Acting"}
)


@dataclass(frozen=True)
class SeatHoldingRecord:
    division_key: str
    location_name: str
    first_sitting_date: date
    last_sitting_date: date
    sitting_count: int
    speaker_id: int


def get_division_key(location_name: str) -> str:
    collapsed = _SEPARATOR_RE.sub(" ", location_name).strip(" ")
    return _DIVISION_SUFFIX_RE.sub("", collapsed).lower()


def build_seat_holding_records(
    attendance_seat_rows: list[AttendanceSeatRow],
) -> list[SeatHoldingRecord]:
    division_key_and_speaker_id_to_dated_names: dict[
        tuple[str, int], list[tuple[date, str]]
    ] = {}
    for attendance_seat_row in attendance_seat_rows:
        if attendance_seat_row.location_name in _NON_DIVISION_LOCATION_NAMES:
            continue
        sitting_date = parse_sitting_date(attendance_seat_row.sitting_date).date()
        division_key_and_speaker_id_to_dated_names.setdefault(
            (
                get_division_key(attendance_seat_row.location_name),
                attendance_seat_row.speaker_id,
            ),
            [],
        ).append((sitting_date, attendance_seat_row.location_name))

    seat_holding_records = []
    for (
        division_key,
        speaker_id,
    ), dated_names in division_key_and_speaker_id_to_dated_names.items():
        first_sitting_date, first_location_name = min(dated_names)
        sitting_dates = {sitting_date for sitting_date, _ in dated_names}
        seat_holding_records.append(
            SeatHoldingRecord(
                division_key,
                first_location_name,
                first_sitting_date,
                max(sitting_dates),
                len(sitting_dates),
                speaker_id,
            )
        )
    return sorted(
        seat_holding_records,
        key=lambda record: (record.speaker_id, record.division_key),
    )
