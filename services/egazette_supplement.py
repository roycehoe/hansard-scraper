import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from enums import EgazetteSupplementKind
from exceptions import HansardEgazetteSupplementError
from utils.bill_number import normalize_bill_number

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_PATTERN = (
    rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s*(?P<month>{_MONTHS})\s*(?P<year>\d{{4}})"
)
BILL_NUMBER_LINE = re.compile(r"Bill\s*No\.\s*(\d+)/(\d{2,4})(?:\.|\s*\[)")
_FIRST_READING = re.compile(rf"Read\s*the\s*first\s*time\s*on\s*{_DATE_PATTERN}")
_PASSING = re.compile(rf"passed\s+by\s+Parliament\s+on\s+{_DATE_PATTERN}")
_ACT_NUMBER = re.compile(r"\bNo\.\s*(\d+)\s*of\s*(\d{4})\.")
_TITLE_BOUNDARY = re.compile(
    r"^\d+$|(—|President\.|I assent\.|\d{4}\.|\d{4} at \d+ [ap]m\.|\[\d{4})$"
)
_TITLE_END = "Bill"


@dataclass(frozen=True)
class ParsedEgazetteSupplement:
    printed_title: str
    printed_bill_number: str
    bill_number: str
    first_reading_date: date
    passing_date: Optional[date]
    printed_act_number: Optional[str]


_PRINTED_DATE_FORMAT = "%d %B %Y"


def _build_date(date_match: re.Match[str]) -> date:
    return datetime.strptime(
        f"{date_match.group('day')} {date_match.group('month')} {date_match.group('year')}",
        _PRINTED_DATE_FORMAT,
    ).date()


def get_bill_number(printed_bill_number: str) -> str:
    bill_number = normalize_bill_number(printed_bill_number)
    if bill_number is None:
        raise HansardEgazetteSupplementError(
            f"Bill number {printed_bill_number!r} is not N/YY or N/YYYY"
        )
    return bill_number


def _get_printed_title(text_before_bill_number: str) -> str:
    title_lines: list[str] = []
    for line in reversed(text_before_bill_number.splitlines()):
        stripped_line = line.strip()
        if not stripped_line:
            break
        if _TITLE_BOUNDARY.search(stripped_line):
            break
        title_lines.insert(0, stripped_line)
    for line_index, title_line in enumerate(title_lines):
        if title_line.endswith(_TITLE_END):
            return " ".join(title_lines[: line_index + 1])
    return " ".join(title_lines)


def parse_egazette_supplement_text(
    text: str, supplement_kind: EgazetteSupplementKind
) -> ParsedEgazetteSupplement:
    bill_number_match = BILL_NUMBER_LINE.search(text)
    if bill_number_match is None:
        raise HansardEgazetteSupplementError("No Bill No. line found in the text")
    first_reading_match = _FIRST_READING.search(text, bill_number_match.end())
    if first_reading_match is None:
        raise HansardEgazetteSupplementError("No first reading date found in the text")
    printed_title = _get_printed_title(text[: bill_number_match.start()])
    if not printed_title:
        raise HansardEgazetteSupplementError("No title found above the Bill No. line")
    printed_bill_number = f"{bill_number_match.group(1)}/{bill_number_match.group(2)}"
    if supplement_kind == EgazetteSupplementKind.BILLS:
        return ParsedEgazetteSupplement(
            printed_title=printed_title,
            printed_bill_number=printed_bill_number,
            bill_number=get_bill_number(printed_bill_number),
            first_reading_date=_build_date(first_reading_match),
            passing_date=None,
            printed_act_number=None,
        )
    passing_match = _PASSING.search(text)
    act_number_match = _ACT_NUMBER.search(text)
    return ParsedEgazetteSupplement(
        printed_title=printed_title,
        printed_bill_number=printed_bill_number,
        bill_number=get_bill_number(printed_bill_number),
        first_reading_date=_build_date(first_reading_match),
        passing_date=None if passing_match is None else _build_date(passing_match),
        printed_act_number=(
            None
            if act_number_match is None
            else f"{act_number_match.group(1)} of {act_number_match.group(2)}"
        ),
    )
