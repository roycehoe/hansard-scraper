import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from settings import settings

_SITTING_DATE_FORMAT = "%d-%m-%Y"


@dataclass(frozen=True)
class MonthWindow:
    first_date: date
    last_date: date


def get_month_windows(first_date: date, last_date: date) -> list[MonthWindow]:
    month_windows = []
    window_first_date = first_date
    while window_first_date <= last_date:
        month_last_date = date(
            window_first_date.year, window_first_date.month, calendar.monthrange(window_first_date.year, window_first_date.month)[1]
        )
        window_last_date = min(month_last_date, last_date)
        month_windows.append(MonthWindow(window_first_date, window_last_date))
        window_first_date = window_last_date + timedelta(days=1)
    return month_windows


def get_sitting_date_key(sitting_date: date) -> str:
    return f"{sitting_date.day}-{sitting_date.month}-{sitting_date.year}"


def parse_sitting_date(sitting_date: str) -> datetime:
    return datetime.strptime(sitting_date, _SITTING_DATE_FORMAT)


def get_zero_padded_sitting_date(sitting_date: str) -> str:
    return parse_sitting_date(sitting_date).strftime(_SITTING_DATE_FORMAT)


def is_new_sitting_date_format(sitting_date: str) -> bool:
    return parse_sitting_date(sitting_date) >= settings.sitting_date_format_change
