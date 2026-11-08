import re
from typing import Optional

_BILL_NUMBER_PATTERN = re.compile(r"^(\d+)/(\d{2}|\d{4})$")
_TWO_DIGIT_YEAR_PIVOT = 50
_TWENTIETH_CENTURY_START = 1900
_TWENTY_FIRST_CENTURY_START = 2000
_TWO_DIGIT_YEAR_LENGTH = 2


def get_full_year(short_year: int) -> int:
    if short_year >= _TWO_DIGIT_YEAR_PIVOT:
        return _TWENTIETH_CENTURY_START + short_year
    return _TWENTY_FIRST_CENTURY_START + short_year


def normalize_bill_number(printed_bill_number: str) -> Optional[str]:
    match = _BILL_NUMBER_PATTERN.match(printed_bill_number.strip())
    if match is None:
        return None
    number, year = match.group(1), match.group(2)
    if len(year) == _TWO_DIGIT_YEAR_LENGTH:
        return f"{int(number)}/{get_full_year(int(year))}"
    return f"{int(number)}/{year}"
