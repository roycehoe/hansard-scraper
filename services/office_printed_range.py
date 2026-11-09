from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from crud.attendance_office import AttendanceOfficeSittingRow
from crud.office_printed_range import OfficePrintedRangeRow
from database.office_printed_range import OfficePrintedRange
from utils.office_printed_range_update import OfficePrintedRangeUpdate
from utils.sitting_dates import parse_sitting_date


@dataclass(frozen=True)
class OfficePrintedRangeChanges:
    office_printed_ranges: list[OfficePrintedRange]
    office_printed_range_updates: list[OfficePrintedRangeUpdate]


def _split_into_runs(
    sorted_attendance_office_sitting_rows: list[AttendanceOfficeSittingRow],
    row_id_to_position: dict[int, int],
) -> list[list[AttendanceOfficeSittingRow]]:
    runs: list[list[AttendanceOfficeSittingRow]] = []
    for attendance_office_sitting_row in sorted_attendance_office_sitting_rows:
        if not runs:
            runs.append([attendance_office_sitting_row])
            continue
        last_row = runs[-1][-1]
        if (
            row_id_to_position[attendance_office_sitting_row.id]
            == row_id_to_position[last_row.id] + 1
            and attendance_office_sitting_row.office_printed == last_row.office_printed
        ):
            runs[-1].append(attendance_office_sitting_row)
            continue
        runs.append([attendance_office_sitting_row])
    return runs


def build_office_printed_ranges(
    attendance_office_sitting_rows: list[AttendanceOfficeSittingRow],
    sorted_sitting_dates: list[datetime],
    built_at: datetime,
) -> list[OfficePrintedRange]:
    sitting_date_to_position = {
        sitting_date: position
        for position, sitting_date in enumerate(sorted_sitting_dates)
    }
    row_id_to_position = {
        attendance_office_sitting_row.id: sitting_date_to_position[
            parse_sitting_date(attendance_office_sitting_row.sitting_date)
        ]
        for attendance_office_sitting_row in attendance_office_sitting_rows
    }
    speaker_id_to_rows: defaultdict[int, list[AttendanceOfficeSittingRow]] = (
        defaultdict(list)
    )
    for attendance_office_sitting_row in attendance_office_sitting_rows:
        if attendance_office_sitting_row.speaker_id is None:
            continue
        speaker_id_to_rows[attendance_office_sitting_row.speaker_id].append(
            attendance_office_sitting_row
        )
    office_printed_ranges = []
    for speaker_id in sorted(speaker_id_to_rows):
        sorted_rows = sorted(
            speaker_id_to_rows[speaker_id],
            key=lambda attendance_office_sitting_row: row_id_to_position[
                attendance_office_sitting_row.id
            ],
        )
        for run in _split_into_runs(sorted_rows, row_id_to_position):
            first_row = run[0]
            last_row = run[-1]
            office_printed_ranges.append(
                OfficePrintedRange(
                    office_printed=first_row.office_printed,
                    office_class=first_row.office_class,
                    sitting_count=len(run),
                    first_sitting_date=sorted_sitting_dates[
                        row_id_to_position[first_row.id]
                    ],
                    last_sitting_date=sorted_sitting_dates[
                        row_id_to_position[last_row.id]
                    ],
                    built_at=built_at,
                    speaker_id=speaker_id,
                    first_attendance_office_id=first_row.id,
                    last_attendance_office_id=last_row.id,
                )
            )
    return office_printed_ranges


def get_office_printed_range_changes(
    attendance_office_sitting_rows: list[AttendanceOfficeSittingRow],
    office_printed_range_rows: list[OfficePrintedRangeRow],
    sorted_sitting_dates: list[datetime],
    built_at: datetime,
) -> OfficePrintedRangeChanges:
    sitting_date_to_position = {
        sitting_date: position
        for position, sitting_date in enumerate(sorted_sitting_dates)
    }
    speaker_id_to_latest_range_row: dict[int, OfficePrintedRangeRow] = {}
    for office_printed_range_row in office_printed_range_rows:
        latest_range_row = speaker_id_to_latest_range_row.get(
            office_printed_range_row.speaker_id
        )
        if (
            latest_range_row is None
            or latest_range_row.last_sitting_date
            < office_printed_range_row.last_sitting_date
        ):
            speaker_id_to_latest_range_row[office_printed_range_row.speaker_id] = (
                office_printed_range_row
            )
    new_office_printed_ranges = []
    office_printed_range_updates = []
    for window_range in build_office_printed_ranges(
        attendance_office_sitting_rows, sorted_sitting_dates, built_at
    ):
        latest_range_row = speaker_id_to_latest_range_row.pop(
            window_range.speaker_id, None
        )
        if latest_range_row is None:
            new_office_printed_ranges.append(window_range)
            continue
        position = sitting_date_to_position[window_range.first_sitting_date]
        if position == 0:
            new_office_printed_ranges.append(window_range)
            continue
        if latest_range_row.office_printed != window_range.office_printed:
            new_office_printed_ranges.append(window_range)
            continue
        if latest_range_row.last_sitting_date != sorted_sitting_dates[position - 1]:
            new_office_printed_ranges.append(window_range)
            continue
        office_printed_range_updates.append(
            OfficePrintedRangeUpdate(
                latest_range_row.id,
                window_range.last_attendance_office_id,
                window_range.last_sitting_date,
                latest_range_row.sitting_count + window_range.sitting_count,
                built_at,
            )
        )
    return OfficePrintedRangeChanges(
        new_office_printed_ranges, office_printed_range_updates
    )
