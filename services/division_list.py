import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from itertools import takewhile
from typing import Optional

from bs4 import BeautifulSoup
from bs4.element import NavigableString, PreformattedString, Tag

from enums import DivisionListStatus, DivisionVoteChoice
from utils.division_vote_name import ParsedVoteName

_OPENING_PATTERN = re.compile(
    r"the\s+(?:house|committee)\s+divided|division\s+taken|question\s+put\W*\s*ayes",
    re.IGNORECASE,
)
_HEADING_CELL_PATTERN = re.compile(
    r"^_?(Ayes|Noes|No|Abstentions?|Absention|Abstentations|Absent|Paired)_?[.:]?(?:[- ]*\(?(?:contd|cont|continued)\.?\)?)?[.:]?_?$",
    re.IGNORECASE,
)
_HEADING_WITH_NAME_PATTERN = re.compile(
    r"^_?(Ayes|Noes|Abstentions?|Absention|Absent|Paired)_?\s+(\S.*)$", re.IGNORECASE
)
_CELL_PATTERN = re.compile(r"\S+(?: \S+)*")
_MARKER_PATTERN = re.compile(r"^(?:Column|Page)\s*:?\s*\d+$", re.IGNORECASE)
_NOISE_CELL_PATTERN = re.compile(r"^[-_–—\s]*$")
_NIL = "nil"
_WRAP_WORDS = frozenset({"bin", "binte", "bte", "bt", "b", "s/o", "d/o"})
_TITLE_CELLS = frozenset({"madam", "miss", "mrs", "mr", "dr"})
_HEADING_WORD_TO_VOTE_CHOICE = {
    "ayes": DivisionVoteChoice.AYE,
    "noes": DivisionVoteChoice.NO,
    "no": DivisionVoteChoice.NO,
    "abstention": DivisionVoteChoice.ABSTAIN,
    "abstentions": DivisionVoteChoice.ABSTAIN,
    "absention": DivisionVoteChoice.ABSTAIN,
    "abstentations": DivisionVoteChoice.ABSTAIN,
    "absent": DivisionVoteChoice.ABSENT,
    "paired": DivisionVoteChoice.PAIRED,
}
_INLINE_TAGS = frozenset(
    {
        "a",
        "b",
        "big",
        "em",
        "font",
        "i",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "tt",
        "u",
    }
)
_SKIPPED_TAGS = frozenset({"head", "script", "style"})
_MIN_SENTENCE_WORDS = 3
_MAX_NAME_WORDS = 6
_BLOCK_SEPARATOR = "\n\n"
_LINE_SEPARATOR = "\n"


class _ItemKind(StrEnum):
    PRE = "PRE"
    TABLE = "TABLE"
    IMAGE = "IMAGE"
    TEXT = "TEXT"


@dataclass(frozen=True)
class _Item:
    kind: _ItemKind
    text: str
    table_rows: list[list[list[str]]]


@dataclass(frozen=True)
class _Opening:
    item_index: int
    line_index: int


@dataclass(frozen=True)
class _PreCell:
    column: int
    text: str


@dataclass(frozen=True)
class _PreLineCell:
    offset: int
    text: str


@dataclass
class _NameDraft:
    printed_name: str
    vote_choice: DivisionVoteChoice
    is_wrap_open: bool


@dataclass
class _ListState:
    column_to_section: dict[int, DivisionVoteChoice]
    column_to_name_index: dict[int, int]
    names: list[_NameDraft]
    is_ended: bool
    is_unreadable: bool


@dataclass(frozen=True)
class _ListReading:
    is_unreadable: bool
    printed_list: Optional[str]
    names: list[ParsedVoteName]


@dataclass(frozen=True)
class ParsedDivisionList:
    list_status: DivisionListStatus
    printed_list: Optional[str]
    names: list[ParsedVoteName]


def _get_text_run(run_parts: list[str]) -> str:
    return " ".join("".join(run_parts).split())


def _flush_run(items: list[_Item], run_parts: list[str]) -> None:
    run = _get_text_run(run_parts)
    run_parts.clear()
    if not run:
        return
    if _MARKER_PATTERN.match(run):
        return
    items.append(_Item(_ItemKind.TEXT, run, []))


def _get_cell_lines(table_cell: Tag) -> list[str]:
    paragraphs = [
        paragraph
        for paragraph in table_cell.find_all("p")
        if paragraph.find("p") is None
    ]
    texts = (
        [paragraph.get_text() for paragraph in paragraphs]
        if paragraphs
        else [table_cell.get_text()]
    )
    lines = [" ".join(text.split()) for text in texts]
    return [line for line in lines if line]


def _get_pre_text(pre: Tag) -> str:
    return (
        pre.get_text()
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\xa0", " ")
    )


def _collect_items(parent: Tag, items: list[_Item], run_parts: list[str]) -> None:
    for child in parent.children:
        if isinstance(child, PreformattedString):
            continue
        if isinstance(child, NavigableString):
            run_parts.append(str(child))
            continue
        if not isinstance(child, Tag):
            continue
        if child.name in _SKIPPED_TAGS:
            continue
        if child.name == "pre":
            _flush_run(items, run_parts)
            items.append(_Item(_ItemKind.PRE, _get_pre_text(child), []))
            continue
        if child.name == "table":
            _flush_run(items, run_parts)
            items.append(
                _Item(
                    _ItemKind.TABLE,
                    "",
                    [
                        [_get_cell_lines(table_cell) for table_cell in table_row.find_all("td")]
                        for table_row in child.find_all("tr")
                    ],
                )
            )
            continue
        if child.name == "img":
            _flush_run(items, run_parts)
            items.append(_Item(_ItemKind.IMAGE, "", []))
            continue
        if child.name in _INLINE_TAGS:
            _collect_items(child, items, run_parts)
            continue
        _flush_run(items, run_parts)
        _collect_items(child, items, run_parts)
        _flush_run(items, run_parts)


def _get_items(report_content: str) -> list[_Item]:
    items: list[_Item] = []
    run_parts: list[str] = []
    _collect_items(BeautifulSoup(report_content, "html.parser"), items, run_parts)
    _flush_run(items, run_parts)
    return items


def _get_openings(items: list[_Item]) -> list[_Opening]:
    openings: list[_Opening] = []
    for item_index, item in enumerate(items):
        if item.kind != _ItemKind.PRE and item.kind != _ItemKind.TEXT:
            continue
        openings.extend(
            _Opening(item_index, item.text.count(_LINE_SEPARATOR, 0, match.end()))
            for match in _OPENING_PATTERN.finditer(item.text)
        )
    return openings


def _is_heading_cell(cell: str) -> bool:
    return (
        _HEADING_CELL_PATTERN.match(cell) is not None
        or _HEADING_WITH_NAME_PATTERN.match(cell) is not None
    )


def _is_list_end_cell(cell: str, is_run: bool) -> bool:
    words = cell.split()
    if len(words) > _MAX_NAME_WORDS:
        return True
    if (
        len(words) >= _MIN_SENTENCE_WORDS
        and cell.endswith(".")
        and words[-1][0].islower()
    ):
        return True
    return is_run and len(words) == 1 and cell.endswith((",", ":"))


def _get_last_word(name: str) -> str:
    return name.split()[-1].rstrip(".").lower()


def _set_section(state: _ListState, column: int, heading_word: str) -> None:
    state.column_to_section[column] = _HEADING_WORD_TO_VOTE_CHOICE[heading_word.lower()]
    previous_index = state.column_to_name_index.get(column)
    if previous_index is not None:
        state.names[previous_index].is_wrap_open = False


def _add_cell(state: _ListState, column: int, cell: str, is_run: bool) -> None:
    heading_match = _HEADING_CELL_PATTERN.match(cell)
    heading_with_name_match = _HEADING_WITH_NAME_PATTERN.match(cell)
    if heading_match is not None:
        _set_section(state, column, heading_match.group(1))
        return
    if heading_with_name_match is not None:
        _set_section(state, column, heading_with_name_match.group(1))
        cell = heading_with_name_match.group(2)
        if _HEADING_CELL_PATTERN.match(cell) is not None:
            return
    if _NOISE_CELL_PATTERN.match(cell) is not None or cell.lower().rstrip(".") == _NIL:
        return
    if _is_list_end_cell(cell, is_run):
        state.is_ended = True
        return
    section = state.column_to_section.get(column)
    if section is None:
        state.is_unreadable = True
        return
    previous_index = state.column_to_name_index.get(column)
    if previous_index is not None:
        previous_name = state.names[previous_index]
        if cell.rstrip(".").lower() in _TITLE_CELLS:
            previous_name.printed_name = f"{previous_name.printed_name} {cell}"
            return
        if previous_name.is_wrap_open:
            previous_name.printed_name = f"{previous_name.printed_name} {cell}"
            previous_name.is_wrap_open = False
            return
    state.names.append(_NameDraft(cell, section, _get_last_word(cell) in _WRAP_WORDS))
    state.column_to_name_index[column] = len(state.names) - 1


def _get_list_state() -> _ListState:
    return _ListState({}, {}, [], is_ended=False, is_unreadable=False)


def _get_parsed_names(state: _ListState) -> list[ParsedVoteName]:
    return [
        ParsedVoteName(ordinal, name.printed_name, name.vote_choice)
        for ordinal, name in enumerate(state.names, 1)
    ]


def _is_marker_line(line: str) -> bool:
    return _MARKER_PATTERN.match(line.strip()) is not None


def _get_pre_row_cells(line: str) -> list[_PreLineCell]:
    return [
        _PreLineCell(match.start(), match.group())
        for match in _CELL_PATTERN.finditer(line)
    ]


def get_pre_column_starts(lines: list[str]) -> Optional[list[int]]:
    data_rows: list[list[_PreLineCell]] = []
    for line in lines:
        if not line.strip():
            continue
        if _is_marker_line(line):
            continue
        cells = _get_pre_row_cells(line)
        if any(_is_heading_cell(cell.text) for cell in cells):
            continue
        data_rows.append(cells)
    most_common_counts = Counter(len(cells) for cells in data_rows).most_common(2)
    if not most_common_counts:
        return None
    if len(most_common_counts) > 1 and most_common_counts[0][1] == most_common_counts[1][1]:
        return None
    cell_count = most_common_counts[0][0]
    first_full_row = next(cells for cells in data_rows if len(cells) == cell_count)
    return [cell.offset for cell in first_full_row]


def _get_nearest_column(offset: int, column_starts: list[int]) -> Optional[int]:
    distances = [abs(offset - start) for start in column_starts]
    nearest_distance = min(distances)
    if distances.count(nearest_distance) > 1:
        return None
    return distances.index(nearest_distance)


def _get_row_pre_cells(
    line: str, column_starts: list[int]
) -> Optional[list[_PreCell]]:
    pre_cells: list[_PreCell] = []
    for line_cell in _get_pre_row_cells(line):
        column = _get_nearest_column(line_cell.offset, column_starts)
        if column is None:
            return None
        if pre_cells and pre_cells[-1].column == column:
            pre_cells[-1] = _PreCell(column, f"{pre_cells[-1].text} {line_cell.text}")
            continue
        pre_cells.append(_PreCell(column, line_cell.text))
    return pre_cells


def _read_pre_blocks(pre_blocks: list[list[str]]) -> _ListReading:
    state = _get_list_state()
    block_texts: list[str] = []
    all_block_texts: list[str] = []
    is_geometry_unreadable = False
    for block_lines in pre_blocks:
        pre_lines = [
            line.rstrip()
            for line in block_lines
            if line.strip() and not _is_marker_line(line)
        ]
        all_block_texts.append(_LINE_SEPARATOR.join(pre_lines))
        if state.is_ended or is_geometry_unreadable:
            continue
        column_starts = get_pre_column_starts(pre_lines)
        if column_starts is None:
            is_geometry_unreadable = True
            continue
        read_pre_lines: list[str] = []
        for pre_line in pre_lines:
            pre_cells = _get_row_pre_cells(pre_line, column_starts)
            if pre_cells is None:
                is_geometry_unreadable = True
                break
            for pre_cell in pre_cells:
                _add_cell(state, pre_cell.column, pre_cell.text, is_run=False)
                if state.is_ended:
                    break
            if state.is_ended:
                break
            read_pre_lines.append(pre_line)
        block_texts.append(_LINE_SEPARATOR.join(read_pre_lines))
    if is_geometry_unreadable:
        return _ListReading(True, _BLOCK_SEPARATOR.join(all_block_texts), [])
    return _ListReading(
        state.is_unreadable,
        _BLOCK_SEPARATOR.join(block_texts),
        _get_parsed_names(state),
    )


def _read_tables(tables: list[_Item]) -> _ListReading:
    state = _get_list_state()
    block_texts: list[str] = []
    for table in tables:
        for table_row in table.table_rows:
            for column, lines in enumerate(table_row):
                read_lines: list[str] = []
                for line in lines:
                    _add_cell(state, column, line, is_run=False)
                    if state.is_ended:
                        break
                    read_lines.append(line)
                if read_lines:
                    block_texts.append(_LINE_SEPARATOR.join(read_lines))
                if state.is_ended:
                    break
            if state.is_ended:
                break
        if state.is_ended:
            break
    return _ListReading(
        state.is_unreadable,
        _BLOCK_SEPARATOR.join(block_texts),
        _get_parsed_names(state),
    )


def _read_runs(runs: list[str]) -> _ListReading:
    state = _get_list_state()
    read_runs: list[str] = []
    for run in runs:
        _add_cell(state, 0, run, is_run=True)
        if state.is_ended:
            break
        read_runs.append(run)
    return _ListReading(
        state.is_unreadable,
        _LINE_SEPARATOR.join(read_runs),
        _get_parsed_names(state),
    )


def _read_list(
    following_items: list[_Item], first_block_lines: list[str]
) -> Optional[_ListReading]:
    pre_items = [
        item.text.split(_LINE_SEPARATOR)
        for item in takewhile(
            lambda item: item.kind == _ItemKind.PRE, following_items
        )
    ]
    has_first_block = any(line.strip() for line in first_block_lines)
    if has_first_block:
        return _read_pre_blocks([first_block_lines, *pre_items])
    if not following_items:
        return None
    first_kind = following_items[0].kind
    if first_kind == _ItemKind.PRE:
        return _read_pre_blocks(pre_items)
    if first_kind == _ItemKind.TABLE:
        return _read_tables(
            list(
                takewhile(lambda item: item.kind == _ItemKind.TABLE, following_items)
            )
        )
    if first_kind == _ItemKind.TEXT:
        return _read_runs(
            [
                item.text
                for item in takewhile(
                    lambda item: item.kind == _ItemKind.TEXT, following_items
                )
            ]
        )
    return _ListReading(True, None, [])


def _get_unreadable_list() -> ParsedDivisionList:
    return ParsedDivisionList(DivisionListStatus.LAYOUT_UNREADABLE, None, [])


def get_division_list(
    report_content: Optional[str],
    division_index: int,
    division_count: int,
    ayes: Optional[int],
    noes: Optional[int],
    abstentions: Optional[int],
    absent: Optional[int],
    paired: Optional[int],
) -> ParsedDivisionList:
    if not report_content:
        return _get_unreadable_list()
    items = _get_items(report_content)
    openings = _get_openings(items)
    if len(openings) != division_count or division_index >= len(openings):
        return _get_unreadable_list()
    opening = openings[division_index]
    opening_item = items[opening.item_index]
    first_block_lines = (
        opening_item.text.split(_LINE_SEPARATOR)[opening.line_index + 1 :]
        if opening_item.kind == _ItemKind.PRE
        else []
    )
    list_reading = _read_list(items[opening.item_index + 1 :], first_block_lines)
    if list_reading is None:
        return ParsedDivisionList(DivisionListStatus.NOT_PRINTED, None, [])
    if list_reading.is_unreadable:
        return ParsedDivisionList(
            DivisionListStatus.LAYOUT_UNREADABLE, list_reading.printed_list, []
        )
    if not list_reading.names:
        return ParsedDivisionList(DivisionListStatus.NOT_PRINTED, None, [])
    vote_choice_to_printed_count = {
        DivisionVoteChoice.AYE: ayes,
        DivisionVoteChoice.NO: noes,
        DivisionVoteChoice.ABSTAIN: abstentions,
        DivisionVoteChoice.ABSENT: absent,
        DivisionVoteChoice.PAIRED: paired,
    }
    vote_choice_to_name_count = Counter(name.vote_choice for name in list_reading.names)
    for vote_choice, printed_count in vote_choice_to_printed_count.items():
        if vote_choice_to_name_count[vote_choice] != (printed_count or 0):
            return ParsedDivisionList(
                DivisionListStatus.COUNTS_DISAGREE, list_reading.printed_list, []
            )
    return ParsedDivisionList(
        DivisionListStatus.STORED, list_reading.printed_list, list_reading.names
    )
