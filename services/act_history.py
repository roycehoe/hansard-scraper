import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from enums import ActHistoryDefect, ActHistoryEntryKind
from exceptions import HansardActHistoryError

_HISTORY_START = re.compile(r"^\s*LEGISLATIVE HISTORY\s*$")
_HISTORY_END = re.compile(r"^\s*(Abbreviations|COMPARATIVE TABLE)\s*$")
_PAGE_BREAK_NOISE = (
    re.compile(r"^\s*Informal Consolidation – version in force from \S+\s*$"),
    re.compile(r"^\s*[ivxlc]{1,6}\s*$"),
    re.compile(r"^\s*\d{2}\.\d{2}\.\d{4}\s*$"),
)
_ENTRY_HEAD = re.compile(r"^\s?(\d{1,3})\. (.+)$")
_ENTRY_HEAD_START = re.compile(
    r"(Malay|Act|Ordinance|G\.\s?N|\d{4} |First|Second|\d{1,2}(?: & \d{1,2})? [A-Z][a-z]+\.|M\. |L\.N\.|U\.K\. |British Military Administration )"
)
_MAX_HEAD_INDENT = 1
_CAPITALS_ONLY_LINE = re.compile(r"^\s*[A-Z0-9 ,.()'’&/-]*[A-Z][A-Z0-9 ,.()'’&/-]*$")
_FIELD_LINE = re.compile(r"^\s+(\S.*?)\s+:(?:\s+(\S.*))?$")
_WRAPPED_LABEL_LINE = re.compile(
    r"^\s{1,8}(Readings|Third Readings|Committee|Committee Report|Readings\))$"
)
_QUALIFIER_START = re.compile(
    r"\((?:Consequential |Related )?[Aa]mendments? (?:made|by)"
)
_ENTRY_KIND = re.compile(
    r"^(?P<law_number>L\.N\. \S+(?: \(G\.N\.[^)—]*\)?)?"
    r"|(?:M\. |Malaysian? )?(?:Act|Ordinance) [IVXL\d]+ of \d{4}"
    r"|\d{1,2}(?: & \d{1,2})? (?:Edw|Geo|Will|Vict|Eliz)\.[^—]*?c\. \d+"
    r"|British Military Administration G\.N\. No\. \S+"
    r"|U\.K\. \d{4}, c\. \d+"
    r"|G\.\s?N\.(?: Sp\.)? No\. \S.*?"
    r"|\d{4} Revised Edition"
    r"|(?:First |Second )?(?:\d{4} )?Reprint(?: \(\d{4}\))?)"
    r"(?: \([^)]*\))? — (?P<title>.*)$"
)
_DATE = re.compile(
    r"(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December)(?: (\d{4}))?"
    r"|(?<![\d.])(?P<numeric_day>\d{1,2})\.(?P<numeric_month>\d{1,2})\.(?:(?P<numeric_year>\d{4})|(?P<numeric_short_year>\d{2}))(?!\d)"
)
_TWO_DIGIT_YEAR_PIVOT = 50
_TWENTIETH_CENTURY_START = 1900
_TWENTY_FIRST_CENTURY_START = 2000
_PARENTHESIS = re.compile(r"\([^)]*\)")
_NOTE = re.compile(r"\s+Note:\s")
_DATE_LABEL_PREFIX = re.compile(r"^dates? of ")
_PRINTED_BILL_NUMBER = re.compile(r"^\d+/\d{2,4}$")
_BILL_NUMBER_IN_TEXT = re.compile(r"Bill No\. (\d+/\d{2,4})")
_READING_NAMES = ("first", "second", "third")


@dataclass(frozen=True)
class HistoryEntryBlock:
    ordinal: int
    lines: list[str]
    has_page_break_noise: bool


@dataclass(frozen=True)
class ParsedHistoryEntry:
    ordinal: int
    printed_text: str
    printed_law_number: str
    printed_title: str
    printed_bill_number: Optional[str]
    first_reading_date: Optional[date]
    second_reading_date: Optional[date]
    third_reading_date: Optional[date]
    commencement_date: Optional[date]
    kind: ActHistoryEntryKind
    defects: list[ActHistoryDefect]


@dataclass
class _Field:
    label: str
    value: str


@dataclass(frozen=True)
class _EntryParts:
    head: str
    fields: list[_Field]


def _is_page_break_noise(line: str) -> bool:
    return any(pattern.match(line) for pattern in _PAGE_BREAK_NOISE)


def split_history_entries(sso_code: str, text: str) -> list[HistoryEntryBlock]:
    entry_lines: list[list[str]] = []
    entry_has_noise: list[bool] = []
    is_inside_history = False
    is_inside_entry = False
    has_field = False
    for line in text.replace("\f", "\n").split("\n"):
        if not is_inside_history:
            is_inside_history = _HISTORY_START.match(line) is not None
            continue
        if _HISTORY_END.match(line):
            break
        if _is_page_break_noise(line):
            if is_inside_entry:
                entry_has_noise[-1] = True
            continue
        if not line.strip():
            continue
        head = _ENTRY_HEAD.match(line)
        if (
            head is not None
            and len(line) - len(line.lstrip()) <= _MAX_HEAD_INDENT
            and _ENTRY_HEAD_START.match(head.group(2))
        ):
            if int(head.group(1)) != len(entry_lines) + 1:
                raise HansardActHistoryError(
                    f"Act {sso_code}: entry {head.group(1)} follows entry {len(entry_lines)}"
                )
            entry_lines.append([line.rstrip()])
            entry_has_noise.append(False)
            is_inside_entry = True
            has_field = False
            continue
        if not is_inside_entry:
            continue
        if has_field and _CAPITALS_ONLY_LINE.match(line):
            is_inside_entry = False
            continue
        has_field = has_field or _FIELD_LINE.match(line) is not None
        entry_lines[-1].append(line.rstrip())
    return [
        HistoryEntryBlock(ordinal, lines, has_page_break_noise)
        for ordinal, (lines, has_page_break_noise) in enumerate(
            zip(entry_lines, entry_has_noise, strict=True), start=1
        )
    ]


def _read_entry_parts(block: HistoryEntryBlock) -> _EntryParts:
    head = _ENTRY_HEAD.sub(r"\2", block.lines[0])
    fields: list[_Field] = []
    for line in block.lines[1:]:
        field_match = _FIELD_LINE.match(line)
        if field_match is not None:
            fields.append(_Field(field_match.group(1), field_match.group(2) or ""))
            continue
        if len(fields) == 0:
            head = f"{head} {line.strip()}"
            continue
        if _WRAPPED_LABEL_LINE.match(line):
            fields[-1].label = f"{fields[-1].label} {line.strip()}"
            continue
        fields[-1].value = f"{fields[-1].value} {line.strip()}"
    return _EntryParts(
        re.sub(r"\s+", " ", head),
        [
            _Field(
                _DATE_LABEL_PREFIX.sub(
                    "", re.sub(r"\s+", " ", field.label).strip().lower()
                ),
                _NOTE.split(re.sub(r"\s+", " ", field.value).strip())[0],
            )
            for field in fields
        ],
    )


def _remove_qualifier(head: str) -> str:
    qualifier_start = _QUALIFIER_START.search(head)
    if qualifier_start is None:
        return head
    depth = 0
    for position in range(qualifier_start.start(), len(head)):
        if head[position] == "(":
            depth += 1
        if head[position] == ")":
            depth -= 1
        if depth == 0:
            return head[: qualifier_start.start()] + head[position + 1 :]
    return head[: qualifier_start.start()]


def _get_entry_kind(printed_law_number: str) -> ActHistoryEntryKind:
    if printed_law_number.startswith("L.N.") or printed_law_number.startswith("G."):
        return ActHistoryEntryKind.SUBSIDIARY_LEGISLATION
    if printed_law_number.endswith("Revised Edition"):
        return ActHistoryEntryKind.REVISED_EDITION
    if printed_law_number.startswith("Act "):
        return ActHistoryEntryKind.ACT
    if printed_law_number.startswith("Ordinance "):
        return ActHistoryEntryKind.ORDINANCE
    return ActHistoryEntryKind.OTHER


def _get_reading_names(label: str) -> list[str]:
    if "reading" not in label:
        return []
    return [name for name in _READING_NAMES if name in label]


def _build_date(date_match: re.Match[str]) -> date:
    if date_match.group("numeric_day") is None:
        return datetime.strptime(date_match.group(0), "%d %B %Y").date()
    day = int(date_match.group("numeric_day"))
    month = int(date_match.group("numeric_month"))
    if date_match.group("numeric_year") is not None:
        return date(int(date_match.group("numeric_year")), month, day)
    short_year = int(date_match.group("numeric_short_year"))
    if short_year >= _TWO_DIGIT_YEAR_PIVOT:
        return date(_TWENTIETH_CENTURY_START + short_year, month, day)
    return date(_TWENTY_FIRST_CENTURY_START + short_year, month, day)


def _read_dates(
    sso_code: str, ordinal: int, value: str, defects: list[ActHistoryDefect]
) -> list[Optional[date]]:
    date_matches = list(_DATE.finditer(_PARENTHESIS.sub("", value)))
    if len(date_matches) == 0:
        defects.append(ActHistoryDefect.NO_DATE_PRINTED)
        return []
    dates: list[Optional[date]] = []
    for date_match in date_matches:
        if date_match.group("numeric_day") is None and date_match.group(3) is None:
            defects.append(ActHistoryDefect.MISSING_YEAR)
            dates.append(None)
            continue
        try:
            dates.append(_build_date(date_match))
        except ValueError as error:
            raise HansardActHistoryError(
                f"Act {sso_code}: entry {ordinal} prints the date {date_match.group(0)}"
            ) from error
    return dates


def _read_reading_name_to_date(
    sso_code: str,
    ordinal: int,
    fields: list[_Field],
    defects: list[ActHistoryDefect],
) -> dict[str, Optional[date]]:
    reading_name_to_date: dict[str, Optional[date]] = {}
    for field in fields:
        reading_names = _get_reading_names(field.label)
        if len(reading_names) == 0 or field.value == "":
            continue
        dates = _read_dates(sso_code, ordinal, field.value, defects)
        for position, reading_name in enumerate(reading_names):
            if reading_name in reading_name_to_date:
                continue
            if len(dates) == 0:
                reading_name_to_date[reading_name] = None
                continue
            reading_name_to_date[reading_name] = (
                dates[position] if len(dates) == len(reading_names) else dates[0]
            )
    return reading_name_to_date


def _get_printed_bill_number(fields: list[_Field]) -> Optional[str]:
    for field in fields:
        if field.label == "bill" and _PRINTED_BILL_NUMBER.match(field.value):
            return field.value
        bill_number_match = _BILL_NUMBER_IN_TEXT.search(field.value)
        if bill_number_match is not None:
            return bill_number_match.group(1)
    return None


def _get_commencement_date(
    sso_code: str,
    ordinal: int,
    fields: list[_Field],
    defects: list[ActHistoryDefect],
) -> Optional[date]:
    for field in fields:
        if (field.label == "commencement" or field.label == "operation") and (
            field.value != ""
        ):
            return next(
                iter(_read_dates(sso_code, ordinal, field.value, defects)), None
            )
    return None


def parse_history_entry(sso_code: str, block: HistoryEntryBlock) -> ParsedHistoryEntry:
    entry_parts = _read_entry_parts(block)
    head = re.sub(r"\s+", " ", _remove_qualifier(entry_parts.head)).strip()
    kind_match = _ENTRY_KIND.match(head)
    if kind_match is None:
        raise HansardActHistoryError(
            f"Act {sso_code}: entry {block.ordinal} has the head {head}"
        )
    printed_law_number = kind_match.group("law_number")
    kind = _get_entry_kind(printed_law_number)
    defects: list[ActHistoryDefect] = []
    if block.has_page_break_noise:
        defects.append(ActHistoryDefect.PAGE_BREAK_NOISE)
    if any(field.value == "" for field in entry_parts.fields):
        defects.append(ActHistoryDefect.EMPTY_VALUE)
    reading_name_to_date = _read_reading_name_to_date(
        sso_code, block.ordinal, entry_parts.fields, defects
    )
    commencement_date = _get_commencement_date(
        sso_code, block.ordinal, entry_parts.fields, defects
    )
    if (
        kind == ActHistoryEntryKind.ACT or kind == ActHistoryEntryKind.ORDINANCE
    ) and len(reading_name_to_date) < len(_READING_NAMES):
        defects.append(ActHistoryDefect.MISSING_READING)
    return ParsedHistoryEntry(
        ordinal=block.ordinal,
        printed_text="\n".join(block.lines),
        printed_law_number=printed_law_number,
        printed_title=kind_match.group("title"),
        printed_bill_number=_get_printed_bill_number(entry_parts.fields),
        first_reading_date=reading_name_to_date.get("first"),
        second_reading_date=reading_name_to_date.get("second"),
        third_reading_date=reading_name_to_date.get("third"),
        commencement_date=commencement_date,
        kind=kind,
        defects=list(dict.fromkeys(defects)),
    )
