import re
from dataclasses import dataclass
from typing import Optional, Union

from crud.speech import SpeechParseRow
from enums import DivisionCountSource, SpeechKind, UnreadDivisionReason

_MAX_ROWS_BETWEEN_LIST_AND_TOTAL = 5
_SIDE_AYES = "ayes"
_SIDE_NOES = "noes"
_SIDE_ABSTENTIONS = "abstentions"
_SIDE_ABSENT = "absent"
_SIDE_PAIRED = "paired"
_SIDES = (_SIDE_AYES, _SIDE_NOES, _SIDE_ABSTENTIONS, _SIDE_ABSENT, _SIDE_PAIRED)
_PRINTED_OPENING_PHRASES = (
    "the house divided",
    "the committee divided",
    "division taken",
    "on question put, the house divided",
)
_SPOKEN_TOTAL_PHRASES = (
    "there are now",
    "there are",
    "the result of the division is",
    "the result of the voting is",
)
_PRINTED_LINE_KINDS = frozenset({None, SpeechKind.PROCEDURAL, SpeechKind.SPEECH})
_PRINTED_OPENING_PATTERN = re.compile(
    "^(?:"
    + "|".join(
        r"\s+".join(re.escape(word) for word in phrase.split())
        for phrase in _PRINTED_OPENING_PHRASES
    )
    + r"|question put(?=[\s,:;]*ayes))",
    re.IGNORECASE,
)
_SPOKEN_TOTAL_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(
        r"\s+".join(re.escape(word) for word in phrase.split())
        for phrase in _SPOKEN_TOTAL_PHRASES
    )
    + r")\b",
    re.IGNORECASE,
)
_COUNT_LABEL_REGEX = r"\b(?:ayes|noes|no|abstentions?|absention|absent|paired)\b"
_LABEL_TO_SIDE = {
    "ayes": _SIDE_AYES,
    "noes": _SIDE_NOES,
    "no": _SIDE_NOES,
    "abstention": _SIDE_ABSTENTIONS,
    "abstentions": _SIDE_ABSTENTIONS,
    "absention": _SIDE_ABSTENTIONS,
    "absent": _SIDE_ABSENT,
    "paired": _SIDE_PAIRED,
}
_UNITS_WORD_TO_VALUE = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
}
_TENS_WORD_TO_VALUE = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_NUMBER_WORD_TO_VALUE = {
    "zero": 0,
    "nil": 0,
    "none": 0,
    "no": 0,
    **_UNITS_WORD_TO_VALUE,
    **_TENS_WORD_TO_VALUE,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}
_NUMBER_REGEX = (
    r"\b(?:\d+|(?:"
    + "|".join(_TENS_WORD_TO_VALUE)
    + r")(?:[-\s]+(?:"
    + "|".join(_UNITS_WORD_TO_VALUE)
    + r"))?|"
    + "|".join(
        sorted(
            (word for word in _NUMBER_WORD_TO_VALUE if word not in _TENS_WORD_TO_VALUE),
            key=len,
            reverse=True,
        )
    )
    + r")\b"
)
_SEPARATOR_CHARACTERS = "\\s,;:.\\-\"'“”‘’()"
_SEPARATOR_REGEX = f"[{_SEPARATOR_CHARACTERS}]*(?:and\\b[{_SEPARATOR_CHARACTERS}]*)?"
_NUMBER_PATTERN = re.compile(_NUMBER_REGEX, re.IGNORECASE)
_LABEL_TOKEN_PATTERN = re.compile(
    f"{_SEPARATOR_REGEX}({_COUNT_LABEL_REGEX})", re.IGNORECASE
)
_NUMBER_TOKEN_PATTERN = re.compile(
    f"{_SEPARATOR_REGEX}({_NUMBER_REGEX})", re.IGNORECASE
)
_LIST_HEADING_PATTERN = re.compile(
    r"^(?:ayes|noes|no|abstentions?|absent|paired)\b", re.IGNORECASE
)
_AYES_WORD_PATTERN = re.compile(r"\bayes\b", re.IGNORECASE)
_NUMBER_WORD_SEPARATOR_PATTERN = re.compile(r"[-\s]+")


@dataclass(frozen=True)
class UnreadDivisionRow:
    report_id: int
    speech_ordinal: int
    reason: UnreadDivisionReason
    printed_text: str


@dataclass(frozen=True)
class ParsedDivision:
    report_division_number: int
    speech_ordinal: int
    count_source: DivisionCountSource
    printed_counts: str
    ayes: Optional[int]
    noes: Optional[int]
    abstentions: Optional[int]
    absent: Optional[int]
    paired: Optional[int]
    merged_total_ordinal: Optional[int]


@dataclass(frozen=True)
class ReportDivisions:
    divisions: list[ParsedDivision]
    unread_rows: list[UnreadDivisionRow]


@dataclass(frozen=True)
class _CountSpan:
    end: int
    side_to_value: dict[str, int]
    is_repeated_label: bool


@dataclass(frozen=True)
class _CountLine:
    position: int
    speech_ordinal: int
    count_source: DivisionCountSource
    printed_counts: str
    side_to_value: dict[str, int]


def _get_number_value(text: str) -> int:
    if text.isdigit():
        return int(text)
    return sum(
        _NUMBER_WORD_TO_VALUE[word]
        for word in _NUMBER_WORD_SEPARATOR_PATTERN.split(text.lower())
    )


def _read_pairs(text: str, start: int, is_label_first: bool) -> Optional[_CountSpan]:
    first_pattern = _LABEL_TOKEN_PATTERN if is_label_first else _NUMBER_TOKEN_PATTERN
    second_pattern = _NUMBER_TOKEN_PATTERN if is_label_first else _LABEL_TOKEN_PATTERN
    position = start
    end: Optional[int] = None
    side_to_value: dict[str, int] = {}
    is_repeated_label = False
    while True:
        first = first_pattern.match(text, position)
        if first is None:
            break
        second = second_pattern.match(text, first.end())
        if second is None:
            break
        label, number = (first, second) if is_label_first else (second, first)
        side = _LABEL_TO_SIDE[label.group(1).lower()]
        if side in side_to_value:
            is_repeated_label = True
        else:
            side_to_value[side] = _get_number_value(number.group(1))
        position = second.end()
        end = second.end()
    if end is None:
        return None
    return _CountSpan(end, side_to_value, is_repeated_label)


def _read_count_span(text: str, start: int) -> Optional[_CountSpan]:
    label_first_span = _read_pairs(text, start, is_label_first=True)
    if label_first_span is not None:
        return label_first_span
    return _read_pairs(text, start, is_label_first=False)


def _is_division_span(side_to_value: dict[str, int]) -> bool:
    return _SIDE_AYES in side_to_value and len(side_to_value) > 1


def _get_printed_line(
    row: SpeechParseRow, position: int, opening: re.Match[str]
) -> Union[_CountLine, UnreadDivisionRow]:
    if row.kind not in _PRINTED_LINE_KINDS:
        return UnreadDivisionRow(
            row.report_id,
            row.ordinal,
            UnreadDivisionReason.OPENING_IN_ROW_OF_OTHER_KIND,
            row.transcript,
        )
    stripped = row.transcript.lstrip()
    span = _read_count_span(stripped, opening.end())
    if span is not None and span.is_repeated_label:
        return UnreadDivisionRow(
            row.report_id,
            row.ordinal,
            UnreadDivisionReason.REPEATED_COUNT_LABEL,
            row.transcript,
        )
    if span is None or not _is_division_span(span.side_to_value):
        return UnreadDivisionRow(
            row.report_id,
            row.ordinal,
            UnreadDivisionReason.OPENING_WITHOUT_COUNTS,
            row.transcript,
        )
    return _CountLine(
        position,
        row.ordinal,
        DivisionCountSource.PRINTED_LINE,
        stripped[: span.end],
        span.side_to_value,
    )


def _get_spoken_total(
    row: SpeechParseRow, position: int
) -> Optional[Union[_CountLine, UnreadDivisionRow]]:
    stripped = row.transcript.lstrip()
    phrase_matches = list(_SPOKEN_TOTAL_PATTERN.finditer(stripped))
    span_and_read_starts = [(match.start(), match.end()) for match in phrase_matches]
    span_and_read_starts.append((0, 0))
    for span_start, read_start in span_and_read_starts:
        span = _read_count_span(stripped, read_start)
        if span is None or not _is_division_span(span.side_to_value):
            continue
        is_row_start_read = read_start == 0
        if is_row_start_read and (
            _NUMBER_PATTERN.match(stripped) is None
            or next(iter(span.side_to_value)) != _SIDE_AYES
        ):
            continue
        if span.is_repeated_label:
            return UnreadDivisionRow(
                row.report_id,
                row.ordinal,
                UnreadDivisionReason.REPEATED_COUNT_LABEL,
                row.transcript,
            )
        return _CountLine(
            position,
            row.ordinal,
            DivisionCountSource.SPOKEN_TOTAL,
            stripped[span_start : span.end],
            span.side_to_value,
        )
    if _AYES_WORD_PATTERN.search(stripped) is None:
        return None
    if len(phrase_matches) == 0 and _NUMBER_PATTERN.match(stripped) is None:
        return None
    return UnreadDivisionRow(
        row.report_id,
        row.ordinal,
        UnreadDivisionReason.TOTAL_WITHOUT_SECOND_COUNT,
        row.transcript,
    )


def _get_count_line(
    row: SpeechParseRow, position: int
) -> Optional[Union[_CountLine, UnreadDivisionRow]]:
    opening = _PRINTED_OPENING_PATTERN.match(row.transcript.lstrip())
    if opening is not None:
        return _get_printed_line(row, position, opening)
    if row.kind != SpeechKind.SPEECH:
        return None
    return _get_spoken_total(row, position)


def _get_last_list_position(
    speech_parse_rows: list[SpeechParseRow],
    position: int,
    line_positions: frozenset[int],
) -> int:
    last_position = position
    for next_position in range(position + 1, len(speech_parse_rows)):
        next_row = speech_parse_rows[next_position]
        if next_row.kind == SpeechKind.SPEECH:
            break
        if next_row.speaker is not None:
            break
        if next_row.kind == SpeechKind.HEADING:
            break
        if (
            next_row.kind == SpeechKind.PROCEDURAL
            and _LIST_HEADING_PATTERN.match(next_row.transcript.lstrip()) is None
        ):
            break
        if next_position in line_positions:
            break
        last_position = next_position
    return last_position


def _is_count_disagreement(
    side_to_value: dict[str, int], other_side_to_value: dict[str, int]
) -> bool:
    return any(
        side in side_to_value
        and side in other_side_to_value
        and side_to_value[side] != other_side_to_value[side]
        for side in _SIDES
    )


def get_report_divisions(speech_parse_rows: list[SpeechParseRow]) -> ReportDivisions:
    count_lines: list[_CountLine] = []
    unread_rows: list[UnreadDivisionRow] = []
    for position, row in enumerate(speech_parse_rows):
        count_line = _get_count_line(row, position)
        if count_line is None:
            continue
        if isinstance(count_line, UnreadDivisionRow):
            unread_rows.append(count_line)
            continue
        count_lines.append(count_line)

    line_positions = frozenset(count_line.position for count_line in count_lines)
    printed_position_to_total_ordinal: dict[int, int] = {}
    merged_total_positions: set[int] = set()
    for count_line, next_line in zip(count_lines, count_lines[1:]):
        if count_line.count_source != DivisionCountSource.PRINTED_LINE:
            continue
        if next_line.count_source != DivisionCountSource.SPOKEN_TOTAL:
            continue
        last_list_position = _get_last_list_position(
            speech_parse_rows, count_line.position, line_positions
        )
        if next_line.position > last_list_position + _MAX_ROWS_BETWEEN_LIST_AND_TOTAL:
            continue
        printed_position_to_total_ordinal[count_line.position] = (
            next_line.speech_ordinal
        )
        merged_total_positions.add(next_line.position)
        if _is_count_disagreement(count_line.side_to_value, next_line.side_to_value):
            total_row = speech_parse_rows[next_line.position]
            unread_rows.append(
                UnreadDivisionRow(
                    total_row.report_id,
                    total_row.ordinal,
                    UnreadDivisionReason.MERGED_COUNTS_DIFFER,
                    total_row.transcript,
                )
            )

    unmerged_count_lines = [
        count_line
        for count_line in count_lines
        if count_line.position not in merged_total_positions
    ]
    divisions = [
        ParsedDivision(
            report_division_number=number,
            speech_ordinal=count_line.speech_ordinal,
            count_source=count_line.count_source,
            printed_counts=count_line.printed_counts,
            ayes=count_line.side_to_value.get(_SIDE_AYES),
            noes=count_line.side_to_value.get(_SIDE_NOES),
            abstentions=count_line.side_to_value.get(_SIDE_ABSTENTIONS),
            absent=count_line.side_to_value.get(_SIDE_ABSENT),
            paired=count_line.side_to_value.get(_SIDE_PAIRED),
            merged_total_ordinal=printed_position_to_total_ordinal.get(
                count_line.position
            ),
        )
        for number, count_line in enumerate(unmerged_count_lines, 1)
    ]
    return ReportDivisions(
        divisions, sorted(unread_rows, key=lambda unread: unread.speech_ordinal)
    )
