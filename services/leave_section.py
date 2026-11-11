import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

from enums import LeaveEntryFormat, LeaveNameSource, LeaveYearSource
from schemas.leave_date_misprint import LeaveDateMisprint
from utils.leave_entry import (
    MONTH_NAME_TO_NUMBER,
    DayAndMonth,
    LeaveDates,
    LeaveEntry,
    get_candidate_years,
    get_nearest_year_dates,
)
from utils.names import strip_title

_SECTION_HEADING_RE = re.compile(
    r"^#*\s*(?:\*\*)?\s*permission\s+to\s+members?\s+(?:to\s+)?be\s+absent\s*(?:\*\*)?\s*:?\s*(?:\*\*)?\s*$",
    re.IGNORECASE,
)
_SIGNATURE_LINE_RE = re.compile(r"^\|?\s*_?(?:Deputy )?Speaker")
_CAPITAL_SIGNATURE_LINE_RE = re.compile(r"^\|\s*\|?\s*\(?[A-Z .]{6,}\)?,?\s*$")
_GLUED_BOLD_HEADING_RE = re.compile(r"\s*\*\*[A-Z].*$")
_NUMBERED_ITEM_LINE_RE = re.compile(r"^\([ivxlc]+\)\s")
_PREAMBLE_LINE_RE = re.compile(
    r"^(?:Under the provisions?\b|The following Member|\*\*Mr Speaker|Mr Speaker|I have|---)"
)
_CONSTITUENCY_BRACKET_RE = re.compile(r"\([^)]*\)")
_MONTH_PATTERN = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?"
_DAY_PATTERN = r"(?<!\d)\d{1,2}(?:\s?(?:st|nd|rd|th))?"
_RANGE_RE = re.compile(
    rf"(?:(?:from|on)\s+)?(?P<start>(?P<start_day>{_DAY_PATTERN})(?:\s+(?P<start_month>{_MONTH_PATTERN}))?(?:,?\s*(?P<start_year>\d{{4}}))?)"
    rf"\s*,?\s+to\s+(?P<end>(?P<end_day>{_DAY_PATTERN})(?:\s+(?P<end_month>{_MONTH_PATTERN}))?(?:,?\s*(?P<end_year>\d{{4}}))?)",
    re.IGNORECASE,
)
_NUMBER_WORD_TO_COUNT = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
}
_NUMBER_WORD_PATTERN = "|".join(_NUMBER_WORD_TO_COUNT)
_DURATION_START_PATTERN = rf"(?:for\s+(?:a\s+period\s+of\s+)?)?(?:\d+|{_NUMBER_WORD_PATTERN})\s+(?:day|week|month|year)s?\b"
_DATE_PART_START_RE = re.compile(
    rf"(?:\s*-+\s*|\s*[–—]\s*|,\s*|\s+)(?=from\b|on\s+{_DAY_PATTERN}|{_DURATION_START_PATTERN}|{_DAY_PATTERN}\s*(?:{_MONTH_PATTERN}|to\b|and\b|,))",
    re.IGNORECASE,
)
_DAY_LIST_RE = re.compile(
    rf"(?:on\s+)?(?P<days>{_DAY_PATTERN}(?:\s*(?:,|and)\s*{_DAY_PATTERN})+)\s+(?P<month>{_MONTH_PATTERN}),?\s*(?P<year>\d{{4}})",
    re.IGNORECASE,
)
_SINGLE_DAY_RE = re.compile(
    rf"^(?:on\s+)?(?P<day>{_DAY_PATTERN})\s+(?P<month>{_MONTH_PATTERN}),?\s*(?P<year>\d{{4}})",
    re.IGNORECASE,
)
_DAY_ITEM_RE = re.compile(
    rf"(?:on\s+)?(?P<days>{_DAY_PATTERN}(?:\s*(?:,|and)\s*{_DAY_PATTERN})*)\s+(?P<month>{_MONTH_PATTERN})(?:,?\s*(?P<year>\d{{4}}))?",
    re.IGNORECASE,
)
_MIN_MIXED_ITEM_COUNT = 2
_DAY_RE = re.compile(_DAY_PATTERN)
_DATE_LEFTOVER_RE = re.compile(r"^[\s,.;]*(?:and[\s,.;]*)*$", re.IGNORECASE)
_NON_DIGIT_RE = re.compile(r"\D")
_DIGIT_RE = re.compile(r"\d")
_NAME_TRAILING_CHARACTERS = ".,-_ "
_PERIOD = "."
_BOLD_MARKER = "**"
_TABLE_CELL_SEPARATOR = "|"
_SECTION_END_PREFIXES = ("#", "[")


def apply_leave_date_misprints(
    date_text: str, leave_date_misprints: list[LeaveDateMisprint]
) -> str:
    for leave_date_misprint in leave_date_misprints:
        date_text = re.sub(
            rf"(?<!\w){re.escape(leave_date_misprint.printed)}(?!\w)",
            leave_date_misprint.reading,
            date_text,
        )
    return date_text


def _is_section_end(line: str, is_entry_seen: bool) -> bool:
    if line.startswith(_SECTION_END_PREFIXES):
        return True
    if _SIGNATURE_LINE_RE.match(line):
        return True
    if _CAPITAL_SIGNATURE_LINE_RE.match(line):
        return True
    if _NUMBERED_ITEM_LINE_RE.match(line):
        return True
    return is_entry_seen and line.startswith(_BOLD_MARKER)


def _join_wrapped_lines(lines: list[str]) -> list[str]:
    joined_lines: list[str] = []
    is_prose_entry_open = False
    for line in lines:
        if _TABLE_CELL_SEPARATOR in line:
            joined_lines.append(line)
            is_prose_entry_open = False
            continue
        if strip_title(line) != line or _CONSTITUENCY_BRACKET_RE.search(line):
            joined_lines.append(line)
            is_prose_entry_open = True
            continue
        if is_prose_entry_open:
            joined_lines[-1] += " " + line
            continue
        joined_lines.append(line)
    return joined_lines


def get_leave_sections(markdown_content: str) -> list[list[str]]:
    sections: list[list[str]] = []
    section_lines: Optional[list[str]] = None
    is_entry_seen = False
    for markdown_line in markdown_content.split("\n"):
        line = markdown_line.strip()
        if _SECTION_HEADING_RE.match(line):
            if section_lines is not None:
                sections.append(section_lines)
            section_lines = []
            is_entry_seen = False
            continue
        if section_lines is None:
            continue
        if not line or _PREAMBLE_LINE_RE.match(line):
            continue
        if _is_section_end(line, is_entry_seen):
            sections.append(section_lines)
            section_lines = None
            continue
        glued_heading = (
            None
            if _TABLE_CELL_SEPARATOR in line or line.startswith(_BOLD_MARKER)
            else _GLUED_BOLD_HEADING_RE.search(line)
        )
        if glued_heading is not None:
            entry_text = line[: glued_heading.start()].strip()
            if entry_text:
                section_lines.append(entry_text)
            sections.append(section_lines)
            section_lines = None
            continue
        section_lines.append(line)
        is_entry_seen = True
    if section_lines is not None:
        sections.append(section_lines)
    return [_join_wrapped_lines(lines) for lines in sections if lines]


@dataclass(frozen=True)
class _ProseEntryParts:
    printed_name: str
    office_printed: Optional[str]
    printed_line: str
    reading_line: str
    date_text: str
    date_text_offset: int


@dataclass(frozen=True)
class _PrintingDates:
    entry_format: LeaveEntryFormat
    printed_from: Optional[str]
    printed_to: Optional[str]
    leave_dates: Optional[LeaveDates]
    year_source: Optional[LeaveYearSource]


@dataclass(frozen=True)
class _DateItemTexts:
    start_day: str
    start_month: Optional[str]
    start_year: Optional[str]
    end_day: str
    end_month: Optional[str]
    end_year: Optional[str]


@dataclass(frozen=True)
class _RangeParts:
    match: re.Match
    start_day: int
    start_month: int
    start_year: Optional[int]
    end_day: int
    end_month: int
    end_year: Optional[int]


@dataclass(frozen=True)
class _RangeYears:
    start_year: Optional[int]
    end_year: Optional[int]


_UNREAD_PRINTING = _PrintingDates(LeaveEntryFormat.UNREAD, None, None, None, None)
_NO_RANGE_YEARS = _RangeYears(None, None)


def _get_prose_entry_parts(
    line: str, leave_date_misprints: list[LeaveDateMisprint]
) -> Optional[_ProseEntryParts]:
    reading_line = apply_leave_date_misprints(line, leave_date_misprints)
    title_length = len(line) - len(strip_title(line))
    bracket = _CONSTITUENCY_BRACKET_RE.search(line, title_length)
    search_start = title_length if bracket is None else bracket.end()
    match = _DATE_PART_START_RE.search(reading_line, search_start)
    if match is None:
        return None
    # NOTE: a misprint before the cut would shift the offsets, so that line goes to UNREAD and no name or office is altered
    if reading_line[: match.start()] != line[: match.start()]:
        return None
    name_end = match.start() if bracket is None else bracket.start()
    printed_name = line[:name_end].rstrip(_NAME_TRAILING_CHARACTERS).strip()
    if _DIGIT_RE.search(printed_name):
        return None
    date_text_with_margin = reading_line[match.end() :]
    margin_length = len(date_text_with_margin) - len(date_text_with_margin.lstrip())
    return _ProseEntryParts(
        printed_name=printed_name,
        office_printed=None,
        printed_line=line,
        reading_line=reading_line,
        date_text=date_text_with_margin.strip().rstrip(_PERIOD),
        date_text_offset=match.end() + margin_length,
    )


def _has_date_text_left(date_text: str, matches: list[re.Match]) -> bool:
    remaining_parts = []
    position = 0
    for match in matches:
        remaining_parts.append(date_text[position : match.start()])
        position = match.end()
    remaining_parts.append(date_text[position:])
    return _DATE_LEFTOVER_RE.match("".join(remaining_parts)) is None


def _get_month(month_text: str) -> int:
    return MONTH_NAME_TO_NUMBER[month_text.rstrip(_PERIOD).lower()]


def _get_printed_month(month_text: Optional[str]) -> Optional[int]:
    if month_text is None:
        return None
    return _get_month(month_text)


def _get_day(day_text: str) -> int:
    return int(_NON_DIGIT_RE.sub("", day_text))


def _get_printed_year(year_text: Optional[str]) -> Optional[int]:
    if year_text is None:
        return None
    return int(year_text)


def _get_date_item_texts(match: re.Match) -> _DateItemTexts:
    if match.re is _DAY_ITEM_RE:
        first_day = _DAY_RE.findall(match.group("days"))[0]
        return _DateItemTexts(
            first_day,
            match.group("month"),
            match.group("year"),
            first_day,
            match.group("month"),
            match.group("year"),
        )
    return _DateItemTexts(
        match.group("start_day"),
        match.group("start_month"),
        match.group("start_year"),
        match.group("end_day"),
        match.group("end_month"),
        match.group("end_year"),
    )


def _get_end_month(
    date_item_texts: _DateItemTexts, later_range_parts: Optional[_RangeParts]
) -> Optional[int]:
    printed_end_month = _get_printed_month(date_item_texts.end_month)
    if printed_end_month is not None:
        return printed_end_month
    if later_range_parts is None:
        return None
    return later_range_parts.start_month


def _get_range_years(
    date_item_texts: _DateItemTexts,
    start_day: int,
    start_month: int,
    end_day: int,
    end_month: int,
    later_range_parts: Optional[_RangeParts],
) -> Optional[_RangeYears]:
    printed_start_year = _get_printed_year(date_item_texts.start_year)
    printed_end_year = _get_printed_year(date_item_texts.end_year)
    is_end_earlier = (end_month, end_day) < (start_month, start_day)
    if printed_end_year is not None:
        end_year = printed_end_year
    elif printed_start_year is not None:
        end_year = printed_start_year + 1 if is_end_earlier else printed_start_year
    elif later_range_parts is not None and later_range_parts.start_year is not None:
        is_end_month_after_later_start = end_month > later_range_parts.start_month
        end_year = (
            later_range_parts.start_year - 1
            if is_end_month_after_later_start
            else later_range_parts.start_year
        )
    else:
        return None
    if printed_start_year is not None:
        return _RangeYears(printed_start_year, end_year)
    return _RangeYears(end_year - 1 if is_end_earlier else end_year, end_year)


def _get_range_parts(date_matches: list[re.Match]) -> Optional[list[_RangeParts]]:
    date_items_texts = [_get_date_item_texts(match) for match in date_matches]
    is_year_printed = any(
        date_item_texts.start_year is not None or date_item_texts.end_year is not None
        for date_item_texts in date_items_texts
    )
    range_parts_in_reverse: list[_RangeParts] = []
    later_range_parts: Optional[_RangeParts] = None
    for match, date_item_texts in zip(
        reversed(date_matches), reversed(date_items_texts)
    ):
        end_month = _get_end_month(date_item_texts, later_range_parts)
        if end_month is None:
            return None
        printed_start_month = _get_printed_month(date_item_texts.start_month)
        start_month = end_month if printed_start_month is None else printed_start_month
        start_day = _get_day(date_item_texts.start_day)
        end_day = _get_day(date_item_texts.end_day)
        if is_year_printed:
            range_years = _get_range_years(
                date_item_texts,
                start_day,
                start_month,
                end_day,
                end_month,
                later_range_parts,
            )
            if range_years is None:
                return None
        else:
            range_years = _NO_RANGE_YEARS
        later_range_parts = _RangeParts(
            match,
            start_day,
            start_month,
            range_years.start_year,
            end_day,
            end_month,
            range_years.end_year,
        )
        range_parts_in_reverse.append(later_range_parts)
    return range_parts_in_reverse[::-1]


def _get_range_dates(
    start_day: int,
    start_month: int,
    start_year: int,
    end_day: int,
    end_month: int,
    end_year: int,
) -> Optional[LeaveDates]:
    try:
        return LeaveDates(
            date(start_year, start_month, start_day),
            date(end_year, end_month, end_day),
        )
    except ValueError:
        return None


def _get_printed_text(
    entry_parts: _ProseEntryParts, date_text_start: int, date_text_end: int
) -> Optional[str]:
    start = entry_parts.date_text_offset + date_text_start
    end = entry_parts.date_text_offset + date_text_end
    if entry_parts.printed_line[start:end] != entry_parts.reading_line[start:end]:
        return None
    return entry_parts.reading_line[start:end]


def _get_range_printing(
    range_parts: _RangeParts,
    entry_parts: _ProseEntryParts,
    sitting_date: date,
    entry_format: LeaveEntryFormat,
) -> _PrintingDates:
    if range_parts.start_year is not None and range_parts.end_year is not None:
        leave_dates = _get_range_dates(
            range_parts.start_day,
            range_parts.start_month,
            range_parts.start_year,
            range_parts.end_day,
            range_parts.end_month,
            range_parts.end_year,
        )
        year_source = LeaveYearSource.PRINTED_IN_ENTRY
    else:
        leave_dates = get_nearest_year_dates(
            DayAndMonth(range_parts.start_day, range_parts.start_month),
            DayAndMonth(range_parts.end_day, range_parts.end_month),
            sitting_date,
            get_candidate_years(sitting_date),
        )
        year_source = LeaveYearSource.NEAREST_TO_SITTING
    if leave_dates is None:
        return _UNREAD_PRINTING
    return _PrintingDates(
        entry_format,
        _get_printed_text(entry_parts, *range_parts.match.span("start")),
        _get_printed_text(entry_parts, *range_parts.match.span("end")),
        leave_dates,
        year_source,
    )


def _get_range_printings(
    entry_parts: _ProseEntryParts, sitting_date: date
) -> Optional[list[_PrintingDates]]:
    range_matches = list(_RANGE_RE.finditer(entry_parts.date_text))
    if not range_matches:
        return None
    if _has_date_text_left(entry_parts.date_text, range_matches):
        return None
    range_parts_in_order = _get_range_parts(range_matches)
    if range_parts_in_order is None:
        return [_UNREAD_PRINTING]
    return [
        _get_range_printing(
            range_parts, entry_parts, sitting_date, LeaveEntryFormat.PROSE_RANGE
        )
        for range_parts in range_parts_in_order
    ]


def _get_day_printings(
    entry_parts: _ProseEntryParts,
    match: re.Match,
    month: int,
    year: int,
    entry_format: LeaveEntryFormat,
) -> list[_PrintingDates]:
    days_group_name = "day" if match.re is _SINGLE_DAY_RE else "days"
    printed_from = _get_printed_text(
        entry_parts, match.start(days_group_name), match.end()
    )
    day_printings = []
    for day_text in _DAY_RE.findall(match.group(days_group_name)):
        try:
            day_date = date(year, month, _get_day(day_text))
        except ValueError:
            day_printings.append(_UNREAD_PRINTING)
            continue
        day_printings.append(
            _PrintingDates(
                entry_format,
                printed_from,
                None,
                LeaveDates(day_date, day_date),
                LeaveYearSource.PRINTED_IN_ENTRY,
            )
        )
    return day_printings


def _get_day_list_printings(
    entry_parts: _ProseEntryParts,
) -> Optional[list[_PrintingDates]]:
    day_list_matches = list(_DAY_LIST_RE.finditer(entry_parts.date_text))
    if not day_list_matches:
        return None
    if _has_date_text_left(entry_parts.date_text, day_list_matches):
        return None
    return [
        printing_dates
        for match in day_list_matches
        for printing_dates in _get_day_printings(
            entry_parts,
            match,
            _get_month(match.group("month")),
            int(match.group("year")),
            LeaveEntryFormat.PROSE_DAY_LIST,
        )
    ]


def _get_single_day_printings(
    entry_parts: _ProseEntryParts,
) -> Optional[list[_PrintingDates]]:
    single_day_match = _SINGLE_DAY_RE.match(entry_parts.date_text)
    if single_day_match is None:
        return None
    if _has_date_text_left(entry_parts.date_text, [single_day_match]):
        return None
    return _get_day_printings(
        entry_parts,
        single_day_match,
        _get_month(single_day_match.group("month")),
        int(single_day_match.group("year")),
        LeaveEntryFormat.PROSE_SINGLE_DAY,
    )


def _get_mixed_date_matches(date_text: str) -> Optional[list[re.Match]]:
    range_matches = list(_RANGE_RE.finditer(date_text))
    date_matches = list(range_matches)
    stretch_start = 0
    for range_match in range_matches:
        date_matches.extend(
            _DAY_ITEM_RE.finditer(date_text, stretch_start, range_match.start())
        )
        stretch_start = range_match.end()
    date_matches.extend(_DAY_ITEM_RE.finditer(date_text, stretch_start, len(date_text)))
    date_matches.sort(key=lambda date_match: date_match.start())
    if len(date_matches) < _MIN_MIXED_ITEM_COUNT:
        return None
    if _has_date_text_left(date_text, date_matches):
        return None
    last_date_item_texts = _get_date_item_texts(date_matches[-1])
    if last_date_item_texts.end_year is None:
        return None
    return date_matches


def _get_mixed_printings(
    entry_parts: _ProseEntryParts, sitting_date: date
) -> Optional[list[_PrintingDates]]:
    date_matches = _get_mixed_date_matches(entry_parts.date_text)
    if date_matches is None:
        return None
    range_parts_in_order = _get_range_parts(date_matches)
    if range_parts_in_order is None:
        return [_UNREAD_PRINTING]
    mixed_printings: list[_PrintingDates] = []
    for range_parts in range_parts_in_order:
        if range_parts.match.re is _RANGE_RE:
            mixed_printings.append(
                _get_range_printing(
                    range_parts, entry_parts, sitting_date, LeaveEntryFormat.PROSE_MIXED
                )
            )
            continue
        if range_parts.start_year is None:
            mixed_printings.append(_UNREAD_PRINTING)
            continue
        mixed_printings.extend(
            _get_day_printings(
                entry_parts,
                range_parts.match,
                range_parts.start_month,
                range_parts.start_year,
                LeaveEntryFormat.PROSE_MIXED,
            )
        )
    return mixed_printings


def _get_prose_printings(
    entry_parts: Optional[_ProseEntryParts], sitting_date: date
) -> list[_PrintingDates]:
    if entry_parts is None:
        return [_UNREAD_PRINTING]
    range_printings = _get_range_printings(entry_parts, sitting_date)
    if range_printings is not None:
        return range_printings
    day_list_printings = _get_day_list_printings(entry_parts)
    if day_list_printings is not None:
        return day_list_printings
    single_day_printings = _get_single_day_printings(entry_parts)
    if single_day_printings is not None:
        return single_day_printings
    mixed_printings = _get_mixed_printings(entry_parts, sitting_date)
    if mixed_printings is not None:
        return mixed_printings
    return [_UNREAD_PRINTING]


def build_leave_entries_from_markdown(
    markdown_content: str,
    sitting_date: date,
    leave_date_misprints: list[LeaveDateMisprint],
) -> list[LeaveEntry]:
    leave_entries: list[LeaveEntry] = []
    for section_lines in get_leave_sections(markdown_content):
        for printed_line in section_lines:
            entry_parts = _get_prose_entry_parts(printed_line, leave_date_misprints)
            for printing_dates in _get_prose_printings(entry_parts, sitting_date):
                leave_entries.append(
                    LeaveEntry(
                        ordinal=len(leave_entries) + 1,
                        printed_name=(
                            None if entry_parts is None else entry_parts.printed_name
                        ),
                        carried_name=None,
                        printed_from=printing_dates.printed_from,
                        printed_to=printing_dates.printed_to,
                        printed_line=printed_line,
                        printed_heading_from=None,
                        printed_heading_to=None,
                        office_printed=(
                            None if entry_parts is None else entry_parts.office_printed
                        ),
                        leave_dates=printing_dates.leave_dates,
                        end_text=None,
                        entry_format=printing_dates.entry_format,
                        name_source=(
                            LeaveNameSource.NONE
                            if entry_parts is None
                            else LeaveNameSource.PRINTED
                        ),
                        year_source=printing_dates.year_source,
                    )
                )
    return leave_entries
