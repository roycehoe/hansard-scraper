import re
from collections import Counter
from dataclasses import dataclass
from typing import Optional

from enums import DivisionListStatus, DivisionVoteChoice
from utils.division_vote_name import ParsedVoteName

_OPENING_PATTERN = re.compile(r"a division was taken|the house divided", re.IGNORECASE)
_COUNT_PATTERN = re.compile(
    r"\b(Ayes|Noes|No|Abstentions?|Absention)\b[\s:,]*(\d+(?: \d+)*|nil)\b",
    re.IGNORECASE,
)
_PAGE_HEADER_PATTERN = re.compile(
    r"^\s*N\s?o\.\s*\d+\s+\d{1,2}\s+[A-Za-z]+\s+\d{4}\s+\d+\s*$"
)
_CONTINUED_HEADING_PATTERN = re.compile(
    r"^\s*(Ayes|Noes?|No|Abstentions?)\s*[–-]\s*continued\s*$", re.IGNORECASE
)
_COLUMN_GAP_PATTERN = re.compile(r"\S+(?: \S+)*")
_GLUED_CAPITALS_PATTERN = re.compile(r"(?<=[a-z])(?=[A-Z])")
_DIVISION_MENTION_PATTERN = re.compile(
    r"division bells?|\bdivided\b|\ba division\b", re.IGNORECASE
)
_LABEL_PATTERN = re.compile(r"\b(Ayes|Noes|No|Abstentions?|Absention)\b")
_DIGIT_PATTERN = re.compile(r"\d")
_WHITESPACE_RUN_PATTERN = re.compile(r"\s+")
_NIL = "nil"
_AYES_PREFIX = "ay"
_NOES_PREFIX = "no"
_LABEL_PREFIX_LENGTH = 2
_SENTENCE_END = "."
_COUNT_END_CHARACTERS = frozenset({".", ",", ";"})
_TAB_WIDTH = 8
_MAX_COUNT_WRAP_LINES = 1
_MAX_NAME_WORDS = 6
_MIN_SENTENCE_END_WORD_LENGTH = 3
_MIN_GLUED_BOUNDARIES = 2
_MIN_HEADER_LABEL_COUNT = 2


@dataclass(frozen=True)
class ParsedMinutesDivision:
    ordinal: int
    printed_counts: str
    ayes: int
    noes: int
    abstentions: Optional[int]
    list_status: DivisionListStatus
    printed_list: Optional[str]
    names: list[ParsedVoteName]


@dataclass(frozen=True)
class MinutesTextDivisions:
    divisions: list[ParsedMinutesDivision]
    is_division_mentioned_without_division: bool


@dataclass(frozen=True)
class _PrintedCounts:
    printed_counts: str
    ayes: int
    noes: int
    abstentions: Optional[int]
    last_line_index: int


@dataclass(frozen=True)
class _Token:
    start: int
    text: str


@dataclass(frozen=True)
class _ReadList:
    list_status: DivisionListStatus
    printed_list: Optional[str]
    names: list[ParsedVoteName]
    next_index: int


def _get_vote_choice(label: str) -> DivisionVoteChoice:
    prefix = label[:_LABEL_PREFIX_LENGTH].lower()
    if prefix == _AYES_PREFIX:
        return DivisionVoteChoice.AYE
    if prefix == _NOES_PREFIX:
        return DivisionVoteChoice.NO
    return DivisionVoteChoice.ABSTAIN


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RUN_PATTERN.sub(" ", text).strip()


def _get_count_value(digits: str) -> int:
    if digits.lower() == _NIL:
        return 0
    return int(digits.replace(" ", ""))


def _get_next_line_index(lines: list[str], index: int) -> Optional[int]:
    for next_index in range(index + 1, len(lines)):
        if lines[next_index].strip() != "":
            return next_index
    return None


def _is_header(line: str) -> bool:
    return (
        len(_LABEL_PATTERN.findall(line)) >= _MIN_HEADER_LABEL_COUNT
        and _DIGIT_PATTERN.search(line) is None
    )


def _get_tokens(line: str) -> list[_Token]:
    return [
        _Token(match.start(), match.group())
        for match in _COLUMN_GAP_PATTERN.finditer(line.expandtabs(_TAB_WIDTH))
    ]


def _get_counts(
    lines: list[str], index: int, opening_match: re.Match
) -> Optional[_PrintedCounts]:
    collapsed = _collapse_whitespace(lines[index][opening_match.start() :])
    opening_length = opening_match.end() - opening_match.start()
    last_line_index = index
    wrap_line_count = 0
    while True:
        count_matches = list(_COUNT_PATTERN.finditer(collapsed, opening_length))
        vote_choice_to_count: dict[DivisionVoteChoice, int] = {}
        for count_match in count_matches:
            vote_choice_to_count.setdefault(
                _get_vote_choice(count_match.group(1)),
                _get_count_value(count_match.group(2)),
            )
        is_ayes_and_noes_printed = (
            DivisionVoteChoice.AYE in vote_choice_to_count
            and DivisionVoteChoice.NO in vote_choice_to_count
        )
        if is_ayes_and_noes_printed and collapsed.endswith(_SENTENCE_END):
            break
        if wrap_line_count == _MAX_COUNT_WRAP_LINES:
            break
        next_line_index = _get_next_line_index(lines, last_line_index)
        if next_line_index is None:
            break
        if _is_header(lines[next_line_index]):
            break
        collapsed = f"{collapsed} {_collapse_whitespace(lines[next_line_index])}"
        last_line_index = next_line_index
        wrap_line_count += 1
    if not is_ayes_and_noes_printed:
        return None
    counts_end = count_matches[-1].end()
    following_character = collapsed[counts_end : counts_end + 1]
    return _PrintedCounts(
        printed_counts=collapsed[:counts_end]
        + (following_character if following_character in _COUNT_END_CHARACTERS else ""),
        ayes=vote_choice_to_count[DivisionVoteChoice.AYE],
        noes=vote_choice_to_count[DivisionVoteChoice.NO],
        abstentions=vote_choice_to_count.get(DivisionVoteChoice.ABSTAIN),
        last_line_index=last_line_index,
    )


def _is_list_end(line: str) -> bool:
    tokens = _get_tokens(line)
    if any(len(token.text.split()) > _MAX_NAME_WORDS for token in tokens):
        return True
    if len(tokens) != 1:
        return False
    return (
        tokens[0].text.endswith(_SENTENCE_END)
        and len(tokens[0].text.split()[-1]) >= _MIN_SENTENCE_END_WORD_LENGTH
    )


def _get_list_row_indexes(lines: list[str], header_index: int) -> list[int]:
    row_indexes: list[int] = []
    for index in range(header_index + 1, len(lines)):
        if lines[index].strip() == "":
            continue
        if _is_list_end(lines[index]):
            break
        row_indexes.append(index)
    return row_indexes


def _get_side_to_start(
    first_row: str, header_sides: list[DivisionVoteChoice], counts: _PrintedCounts
) -> Optional[dict[DivisionVoteChoice, int]]:
    tokens = _get_tokens(first_row)
    if len(tokens) > len(header_sides):
        return None
    if len(tokens) == len(header_sides):
        return {
            side: token.start for side, token in zip(header_sides, tokens, strict=True)
        }
    side_to_count = {
        DivisionVoteChoice.AYE: counts.ayes,
        DivisionVoteChoice.NO: counts.noes,
        DivisionVoteChoice.ABSTAIN: counts.abstentions or 0,
    }
    positive_sides = {side for side, count in side_to_count.items() if count > 0}
    leftmost_sides = header_sides[: len(tokens)]
    if positive_sides != set(leftmost_sides):
        return None
    return {
        side: token.start for side, token in zip(leftmost_sides, tokens, strict=True)
    }


def _get_nearest_side(
    token_start: int, side_to_start: dict[DivisionVoteChoice, int]
) -> Optional[DivisionVoteChoice]:
    side_to_distance = {
        side: abs(start - token_start) for side, start in side_to_start.items()
    }
    nearest_distance = min(side_to_distance.values())
    nearest_sides = [
        side
        for side, distance in side_to_distance.items()
        if distance == nearest_distance
    ]
    if len(nearest_sides) != 1:
        return None
    return nearest_sides[0]


def _split_glued_capitals(text: str) -> str:
    parts = _GLUED_CAPITALS_PATTERN.split(text)
    if len(parts) - 1 < _MIN_GLUED_BOUNDARIES:
        return text
    return " ".join(parts)


def _read_names(
    lines: list[str],
    row_indexes: list[int],
    first_side_to_start: dict[DivisionVoteChoice, int],
) -> Optional[list[ParsedVoteName]]:
    side_to_start = dict(first_side_to_start)
    names: list[ParsedVoteName] = []
    for position, line_index in enumerate(row_indexes):
        heading_match = _CONTINUED_HEADING_PATTERN.match(lines[line_index])
        if heading_match is None:
            for token in _get_tokens(lines[line_index]):
                if token.text.lower() == _NIL:
                    continue
                side = _get_nearest_side(token.start, side_to_start)
                if side is None:
                    return None
                names.append(
                    ParsedVoteName(
                        len(names) + 1, _split_glued_capitals(token.text), side
                    )
                )
            continue
        heading_side = _get_vote_choice(heading_match.group(1))
        if heading_side not in side_to_start:
            return None
        if position + 1 == len(row_indexes):
            return None
        next_line = lines[row_indexes[position + 1]]
        if _CONTINUED_HEADING_PATTERN.match(next_line) is not None:
            return None
        expanded_heading = lines[line_index].expandtabs(_TAB_WIDTH)
        heading_start = len(expanded_heading) - len(expanded_heading.lstrip())
        side_to_start[heading_side] = min(
            _get_tokens(next_line), key=lambda token: abs(token.start - heading_start)
        ).start
    return names


def _read_list(lines: list[str], counts: _PrintedCounts) -> _ReadList:
    header_index = _get_next_line_index(lines, counts.last_line_index)
    if header_index is None or not _is_header(lines[header_index]):
        return _ReadList(
            DivisionListStatus.NOT_PRINTED, None, [], counts.last_line_index + 1
        )
    row_indexes = _get_list_row_indexes(lines, header_index)
    end_index = row_indexes[-1] if len(row_indexes) > 0 else header_index
    printed_list = "\n".join(
        line.rstrip() for line in lines[header_index : end_index + 1]
    )
    next_index = end_index + 1
    if len(row_indexes) == 0:
        return _ReadList(
            DivisionListStatus.LAYOUT_UNREADABLE, printed_list, [], next_index
        )
    if _CONTINUED_HEADING_PATTERN.match(lines[row_indexes[0]]) is not None:
        return _ReadList(
            DivisionListStatus.LAYOUT_UNREADABLE, printed_list, [], next_index
        )
    header_sides = [
        _get_vote_choice(label) for label in _LABEL_PATTERN.findall(lines[header_index])
    ]
    side_to_start = _get_side_to_start(lines[row_indexes[0]], header_sides, counts)
    if side_to_start is None:
        return _ReadList(
            DivisionListStatus.LAYOUT_UNREADABLE, printed_list, [], next_index
        )
    names = _read_names(lines, row_indexes, side_to_start)
    if names is None:
        return _ReadList(
            DivisionListStatus.LAYOUT_UNREADABLE, printed_list, [], next_index
        )
    vote_choice_to_name_count = Counter(name.vote_choice for name in names)
    if (
        vote_choice_to_name_count[DivisionVoteChoice.AYE] != counts.ayes
        or vote_choice_to_name_count[DivisionVoteChoice.NO] != counts.noes
        or vote_choice_to_name_count[DivisionVoteChoice.ABSTAIN]
        != (counts.abstentions or 0)
    ):
        return _ReadList(
            DivisionListStatus.COUNTS_DISAGREE, printed_list, [], next_index
        )
    return _ReadList(DivisionListStatus.STORED, printed_list, names, next_index)


def get_minutes_divisions(extracted_text: str) -> MinutesTextDivisions:
    lines = [
        line
        for line in extracted_text.split("\n")
        if _PAGE_HEADER_PATTERN.match(line) is None
    ]
    divisions: list[ParsedMinutesDivision] = []
    opening_count = 0
    index = 0
    while index < len(lines):
        opening_match = _OPENING_PATTERN.search(lines[index])
        if opening_match is None:
            index += 1
            continue
        opening_count += 1
        counts = _get_counts(lines, index, opening_match)
        if counts is None:
            index += 1
            continue
        read_list = _read_list(lines, counts)
        divisions.append(
            ParsedMinutesDivision(
                ordinal=len(divisions) + 1,
                printed_counts=counts.printed_counts,
                ayes=counts.ayes,
                noes=counts.noes,
                abstentions=counts.abstentions,
                list_status=read_list.list_status,
                printed_list=read_list.printed_list,
                names=read_list.names,
            )
        )
        index = read_list.next_index
    is_mentioned_without_division = opening_count > len(divisions) or (
        len(divisions) == 0
        and _DIVISION_MENTION_PATTERN.search(extracted_text) is not None
    )
    return MinutesTextDivisions(divisions, is_mentioned_without_division)
