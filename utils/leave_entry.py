from dataclasses import dataclass
from datetime import date
from typing import Optional, Sequence

from enums import LeaveEntryFormat, LeaveNameSource, LeaveYearSource
from utils.names import normalize_name, strip_title

YEAR_ORDER_BREAK_GROUP = "year_order_break"

_UNMERGED_KEY_PREFIX = "entry"
_OPEN_END_KEY = "open"

MONTH_NAME_TO_NUMBER = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass(frozen=True)
class DayAndMonth:
    day: int
    month: int


@dataclass(frozen=True)
class LeaveDates:
    start_date: date
    end_date: Optional[date]


@dataclass(frozen=True)
class LeaveEntry:
    ordinal: int
    printed_name: Optional[str]
    carried_name: Optional[str]
    printed_from: Optional[str]
    printed_to: Optional[str]
    printed_line: Optional[str]
    printed_heading_from: Optional[str]
    printed_heading_to: Optional[str]
    office_printed: Optional[str]
    leave_dates: Optional[LeaveDates]
    end_text: Optional[str]
    entry_format: LeaveEntryFormat
    name_source: LeaveNameSource
    year_source: Optional[LeaveYearSource]


def get_candidate_years(sitting_date: date) -> list[int]:
    return [sitting_date.year - 1, sitting_date.year, sitting_date.year + 1]


def get_leave_gap_days(
    start_date: date, end_date: Optional[date], sitting_date: date
) -> int:
    if sitting_date < start_date:
        return (start_date - sitting_date).days
    if end_date is None:
        return (sitting_date - start_date).days
    if sitting_date > end_date:
        return (sitting_date - end_date).days
    return 0


def _get_candidate_dates(
    printed_start: DayAndMonth, printed_end: Optional[DayAndMonth], year: int
) -> Optional[LeaveDates]:
    try:
        start_date = date(year, printed_start.month, printed_start.day)
        if printed_end is None:
            return LeaveDates(start_date, None)
        is_end_in_next_year = (printed_end.month, printed_end.day) < (
            printed_start.month,
            printed_start.day,
        )
        end_year = year + 1 if is_end_in_next_year else year
        return LeaveDates(
            start_date, date(end_year, printed_end.month, printed_end.day)
        )
    except ValueError:
        return None


def get_nearest_year_dates(
    printed_start: DayAndMonth,
    printed_end: Optional[DayAndMonth],
    sitting_date: date,
    candidate_years: Sequence[int],
) -> Optional[LeaveDates]:
    candidate_leave_dates = [
        leave_dates
        for year in candidate_years
        if (leave_dates := _get_candidate_dates(printed_start, printed_end, year))
        is not None
    ]
    if not candidate_leave_dates:
        return None
    leave_dates_and_gap_days = [
        (
            leave_dates,
            get_leave_gap_days(
                leave_dates.start_date, leave_dates.end_date, sitting_date
            ),
        )
        for leave_dates in candidate_leave_dates
    ]
    smallest_gap_days = min(gap_days for _, gap_days in leave_dates_and_gap_days)
    nearest_leave_dates = [
        leave_dates
        for leave_dates, gap_days in leave_dates_and_gap_days
        if gap_days == smallest_gap_days
    ]
    if len(nearest_leave_dates) != 1:
        return None
    return nearest_leave_dates[0]


def get_leave_period_key(
    name: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date],
    sitting_id: int,
    ordinal: int,
) -> str:
    if name is None or start_date is None:
        return f"{_UNMERGED_KEY_PREFIX}|{sitting_id}|{ordinal}"
    end_key = _OPEN_END_KEY if end_date is None else end_date.isoformat()
    return f"{' '.join(name.split()).casefold()}|{start_date.isoformat()}|{end_key}"


def is_covering_sitting(
    start_date: Optional[date], end_date: Optional[date], sitting_date: date
) -> Optional[bool]:
    if start_date is None:
        return None
    if end_date is None:
        return start_date <= sitting_date
    return start_date <= sitting_date <= end_date


def get_leave_name_key(name: str) -> str:
    return " ".join(strip_title(normalize_name(name)).split()).casefold()
