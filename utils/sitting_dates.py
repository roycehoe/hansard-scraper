from datetime import datetime

from settings import settings

_SITTING_DATE_FORMAT = "%d-%m-%Y"


def parse_sitting_date(sitting_date: str) -> datetime:
    return datetime.strptime(sitting_date, _SITTING_DATE_FORMAT)


def get_zero_padded_sitting_date(sitting_date: str) -> str:
    return parse_sitting_date(sitting_date).strftime(_SITTING_DATE_FORMAT)


def is_new_sitting_date_format(sitting_date: str) -> bool:
    return parse_sitting_date(sitting_date) >= settings.sitting_date_format_change
