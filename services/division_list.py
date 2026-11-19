import re
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from itertools import groupby, takewhile
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
    r"^_?(Ayes?|Noes|Nose|No|Abstentions?|Absentions?|Abstentations?|Absent|Paired)_?[.:]?(?:[- ]*\(?(?:contd|cont|continued)\.?\)?)?[.:]?_?$",
    re.IGNORECASE,
)
_HEADING_WITH_NAME_PATTERN = re.compile(
    r"^_?(Ayes|Noes|Nose|Abstentions?|Absentions?|Absent|Paired)_?\s+(\S.*)$",
    re.IGNORECASE,
)
_CELL_PATTERN = re.compile(r"\S+(?: \S+)*")
_MARKER_PATTERN = re.compile(r"^(?:Column|Page)\s*:?\s*\d+$", re.IGNORECASE)
_NOISE_CELL_PATTERN = re.compile(r"^[-_–—\s]*$")
_GLUED_HEADING_OR_NIL_PATTERN = re.compile(
    r"\.\s+(?:Ayes|Noes|Nose|No|Abstentions?|Absentions?|Abstentations?|Absent|Paired|Nil)\.?$",
    re.IGNORECASE,
)
_OPENING_AYES_COUNT_PATTERN = re.compile(r"Ayes?\W{0,3}(\d+)", re.IGNORECASE)
_OPENING_NOES_COUNT_PATTERN = re.compile(r"Noe?s?\W{0,3}(\d+)", re.IGNORECASE)
_OPENING_COUNT_LOOKAHEAD = 160
_NIL_CELLS = frozenset({"nil", "nils"})
_WRAP_WORDS = frozenset({"bin", "binte", "bte", "bt", "b", "s/o", "d/o"})
_BIN_ABBREVIATION = "b"
_INITIALS_SEPARATOR = ","
_TAB_SIZE = 8
_MIN_GUTTER_WIDTH = 2
_MIN_NARROW_GUTTER_LINES = 12
_MIN_COLUMN_LINES = 2
_MIN_NARROW_COLUMN_LINES = 5
_HEADING_COLUMN_LEAD = 4
_HEADING_CELL_LEAD_BEFORE_COLUMN = 3
_SPANNING_HEADING_DISTANCE = 6
_MIN_SPANNING_COLUMNS = 2
_MIN_HEADINGS_FOR_COLUMNS = 2
_TITLE_CELLS = frozenset({"madam", "miss", "mrs", "mr", "dr"})
_HEADING_WORD_TO_VOTE_CHOICE = {
    "aye": DivisionVoteChoice.AYE,
    "ayes": DivisionVoteChoice.AYE,
    "noes": DivisionVoteChoice.NO,
    "nose": DivisionVoteChoice.NO,
    "no": DivisionVoteChoice.NO,
    "abstention": DivisionVoteChoice.ABSTAIN,
    "abstentions": DivisionVoteChoice.ABSTAIN,
    "absention": DivisionVoteChoice.ABSTAIN,
    "absentions": DivisionVoteChoice.ABSTAIN,
    "abstentation": DivisionVoteChoice.ABSTAIN,
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
    offset: int
    end: int


@dataclass(frozen=True)
class _PreLineCell:
    offset: int
    text: str


@dataclass(frozen=True)
class _ColumnStart:
    offset: int
    gutter_width: int


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
    return pre.get_text().replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")


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
                        [
                            _get_cell_lines(table_cell)
                            for table_cell in table_row.find_all("td")
                        ]
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


def _is_wrap_open(name: str) -> bool:
    last_word = _get_last_word(name)
    if last_word == _BIN_ABBREVIATION and _INITIALS_SEPARATOR in name:
        return False
    return last_word in _WRAP_WORDS


def _set_section(state: _ListState, column: int, heading_word: str) -> None:
    state.column_to_section[column] = _HEADING_WORD_TO_VOTE_CHOICE[heading_word.lower()]
    state.column_to_name_index.pop(column, None)


def _get_section(state: _ListState, column: int) -> Optional[DivisionVoteChoice]:
    section = state.column_to_section.get(column)
    if section is not None:
        return section
    left_columns = [
        heading_column
        for heading_column in state.column_to_section
        if heading_column < column
    ]
    if not left_columns:
        return None
    return state.column_to_section[max(left_columns)]


def _add_cell(
    state: _ListState, column: int, cell: str, is_run: bool, is_indented: bool
) -> None:
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
    if (
        _NOISE_CELL_PATTERN.match(cell) is not None
        or cell.lower().rstrip(".") in _NIL_CELLS
    ):
        return
    if _GLUED_HEADING_OR_NIL_PATTERN.search(cell) is not None:
        state.is_unreadable = True
        return
    if _is_list_end_cell(cell, is_run):
        state.is_ended = True
        return
    section = _get_section(state, column)
    if section is None:
        state.is_unreadable = True
        return
    previous_index = state.column_to_name_index.get(column)
    if previous_index is not None:
        previous_name = state.names[previous_index]
        if cell.rstrip(".").lower() in _TITLE_CELLS:
            previous_name.printed_name = f"{previous_name.printed_name} {cell}"
            return
        if len(cell.split()) == 1 and _INITIALS_SEPARATOR not in cell:
            previous_name.printed_name = f"{previous_name.printed_name} {cell}"
            previous_name.is_wrap_open = False
            return
        if is_indented and not previous_name.printed_name.endswith("."):
            previous_name.printed_name = f"{previous_name.printed_name} {cell}"
            previous_name.is_wrap_open = False
            return
        if previous_name.is_wrap_open:
            previous_name.printed_name = f"{previous_name.printed_name} {cell}"
            previous_name.is_wrap_open = False
            return
    state.names.append(_NameDraft(cell, section, _is_wrap_open(cell)))
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


def _has_heading_cell(line: str) -> bool:
    return any(_is_heading_cell(cell.text) for cell in _get_pre_row_cells(line))


def _get_column_starts(name_lines: list[str]) -> list[_ColumnStart]:
    width = max((len(line) for line in name_lines), default=0)
    is_blank_at = [
        all(position >= len(line) or line[position].isspace() for line in name_lines)
        for position in range(width)
    ]
    if all(is_blank_at):
        return []
    position = is_blank_at.index(False)
    column_starts = [_ColumnStart(position, 0)]
    for is_blank, run in groupby(is_blank_at[position:]):
        run_width = len(list(run))
        position += run_width
        if not is_blank or position >= width:
            continue
        if run_width >= _MIN_GUTTER_WIDTH or (
            len(name_lines) >= _MIN_NARROW_GUTTER_LINES
        ):
            column_starts.append(_ColumnStart(position, run_width))
    return column_starts


def _is_thin_column(
    column_starts: list[_ColumnStart], index: int, name_lines: list[str]
) -> bool:
    column_start = column_starts[index]
    end = column_starts[index + 1].offset if index + 1 < len(column_starts) else None
    line_count = sum(
        1 for line in name_lines if line[column_start.offset : end].strip()
    )
    if column_start.gutter_width >= _MIN_GUTTER_WIDTH:
        return line_count < _MIN_COLUMN_LINES
    return line_count < _MIN_NARROW_COLUMN_LINES


def _get_column_offsets(name_lines: list[str]) -> list[int]:
    column_starts = _get_column_starts(name_lines)
    while True:
        thin_index = next(
            (
                index
                for index in range(1, len(column_starts))
                if _is_thin_column(column_starts, index, name_lines)
            ),
            None,
        )
        if thin_index is None:
            break
        del column_starts[thin_index]
    return [column_start.offset for column_start in column_starts] or [0]


def _get_heading_column_offsets(lines: list[str]) -> list[int]:
    for line in lines:
        heading_offsets = [
            line_cell.offset
            for line_cell in _get_pre_row_cells(line)
            if _is_heading_cell(line_cell.text)
        ]
        if len(heading_offsets) >= _MIN_HEADINGS_FOR_COLUMNS:
            return [max(offset - _HEADING_COLUMN_LEAD, 0) for offset in heading_offsets]
    return []


def _get_nearest_column(offset: int, column_offsets: list[int]) -> Optional[int]:
    distances = [abs(offset - column_offset) for column_offset in column_offsets]
    nearest_distance = min(distances)
    if distances.count(nearest_distance) > 1:
        return None
    return distances.index(nearest_distance)


def _get_nearest_line_cells(line: str, column_offsets: list[int]) -> list[_PreCell]:
    pre_cells: list[_PreCell] = []
    for line_cell in _get_pre_row_cells(line):
        column = _get_nearest_column(line_cell.offset, column_offsets)
        if column is None:
            return []
        end = line_cell.offset + len(line_cell.text)
        if pre_cells and pre_cells[-1].column == column:
            pre_cells[-1] = _PreCell(
                column,
                f"{pre_cells[-1].text} {line_cell.text}",
                pre_cells[-1].offset,
                end,
            )
            continue
        pre_cells.append(_PreCell(column, line_cell.text, line_cell.offset, end))
    return pre_cells


def _get_column_of(offset: int, column_offsets: list[int]) -> int:
    for column in range(len(column_offsets) - 1, 0, -1):
        if offset >= column_offsets[column]:
            return column
    return 0


def _get_heading_line_cells(line: str, column_offsets: list[int]) -> list[_PreCell]:
    pre_cells: list[_PreCell] = []
    for line_cell in _get_pre_row_cells(line):
        lead = (
            _HEADING_CELL_LEAD_BEFORE_COLUMN if _is_heading_cell(line_cell.text) else 0
        )
        column = _get_column_of(line_cell.offset + lead, column_offsets)
        end = line_cell.offset + len(line_cell.text)
        if pre_cells and pre_cells[-1].column == column:
            pre_cells[-1] = _PreCell(
                column,
                f"{pre_cells[-1].text} {line_cell.text}",
                pre_cells[-1].offset,
                end,
            )
            continue
        pre_cells.append(_PreCell(column, line_cell.text, line_cell.offset, end))
    return pre_cells


def _get_name_line_cells(line: str, column_offsets: list[int]) -> list[_PreCell]:
    pre_cells: list[_PreCell] = []
    bounds = [0, *column_offsets[1:], len(line) + 1]
    for column in range(len(column_offsets)):
        segment = line[bounds[column] : bounds[column + 1]]
        text = " ".join(segment.split())
        if not text:
            continue
        offset = bounds[column] + len(segment) - len(segment.lstrip())
        pre_cells.append(_PreCell(column, text, offset, offset + len(segment.strip())))
    return pre_cells


def _get_modal_offsets(
    line_cells: list[list[_PreCell]], column_offsets: list[int]
) -> list[int]:
    column_to_offset_counts = [Counter() for _ in column_offsets]
    for pre_cells in line_cells:
        for pre_cell in pre_cells:
            if not _is_heading_cell(pre_cell.text):
                column_to_offset_counts[pre_cell.column][pre_cell.offset] += 1
    return [
        offset_counts.most_common(1)[0][0] if offset_counts else column_offset
        for offset_counts, column_offset in zip(column_to_offset_counts, column_offsets)
    ]


def _get_spanning_heading_cells(
    pre_cells: list[_PreCell], column_offsets: list[int]
) -> list[_PreCell]:
    if len(column_offsets) < _MIN_SPANNING_COLUMNS or len(pre_cells) != 1:
        return pre_cells
    heading = pre_cells[0]
    if not _is_heading_cell(heading.text):
        return pre_cells
    distance = min(abs(heading.offset - offset) for offset in column_offsets)
    if distance <= _SPANNING_HEADING_DISTANCE:
        return pre_cells
    return [
        _PreCell(column, heading.text, heading.offset, heading.end)
        for column in range(len(column_offsets))
    ]


def _read_pre_blocks(pre_blocks: list[list[str]]) -> _ListReading:
    state = _get_list_state()
    block_texts: list[str] = []
    for block_lines in pre_blocks:
        if state.is_ended:
            break
        pre_lines = [
            line.rstrip()
            for line in block_lines
            if line.strip() and not _is_marker_line(line)
        ]
        expanded_lines = [line.expandtabs(_TAB_SIZE) for line in pre_lines]
        name_lines = [line for line in expanded_lines if not _has_heading_cell(line)]
        column_offsets = _get_column_offsets(name_lines)
        heading_column_offsets = _get_heading_column_offsets(expanded_lines)
        if len(heading_column_offsets) > len(column_offsets):
            column_offsets = heading_column_offsets
            line_cells = [
                _get_nearest_line_cells(line, column_offsets) for line in expanded_lines
            ]
        else:
            line_cells = [
                _get_heading_line_cells(line, column_offsets)
                if _has_heading_cell(line)
                else _get_name_line_cells(line, column_offsets)
                for line in expanded_lines
            ]
        modal_offsets = _get_modal_offsets(line_cells, column_offsets)
        read_pre_lines: list[str] = []
        for pre_line, line_pre_cells in zip(pre_lines, line_cells):
            pre_cells = _get_spanning_heading_cells(line_pre_cells, column_offsets)
            for pre_cell in pre_cells:
                _add_cell(
                    state,
                    pre_cell.column,
                    pre_cell.text,
                    is_run=False,
                    is_indented=pre_cell.offset > modal_offsets[pre_cell.column],
                )
                if state.is_ended:
                    break
            if state.is_ended:
                break
            read_pre_lines.append(pre_line)
        block_texts.append(_LINE_SEPARATOR.join(read_pre_lines))
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
                    _add_cell(state, column, line, is_run=False, is_indented=False)
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
        _add_cell(state, 0, run, is_run=True, is_indented=False)
        if state.is_ended:
            break
        read_runs.append(run)
    return _ListReading(
        state.is_unreadable,
        _LINE_SEPARATOR.join(read_runs),
        _get_parsed_names(state),
    )


def _get_pre_items(following_items: list[_Item]) -> list[list[str]]:
    pre_items: list[list[str]] = []
    pending_heading: Optional[str] = None
    for index, item in enumerate(following_items):
        if item.kind == _ItemKind.PRE:
            lines = item.text.split(_LINE_SEPARATOR)
            if pending_heading is not None:
                lines = [pending_heading, *lines]
                pending_heading = None
            pre_items.append(lines)
            continue
        is_before_pre = (
            index + 1 < len(following_items)
            and following_items[index + 1].kind == _ItemKind.PRE
        )
        if (
            item.kind == _ItemKind.TEXT
            and pre_items
            and is_before_pre
            and _HEADING_CELL_PATTERN.match(item.text) is not None
        ):
            pending_heading = item.text
            continue
        break
    return pre_items


def _read_list(
    following_items: list[_Item], first_block_lines: list[str]
) -> Optional[_ListReading]:
    pre_items = _get_pre_items(following_items)
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
            list(takewhile(lambda item: item.kind == _ItemKind.TABLE, following_items))
        )
    if first_kind == _ItemKind.TEXT:
        first_line = following_items[0].text.split(_LINE_SEPARATOR)[0].strip()
        if not _is_heading_cell(first_line):
            return None
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


def _get_opening_tail(items: list[_Item], opening: _Opening) -> str:
    lines = items[opening.item_index].text.split(_LINE_SEPARATOR)
    tail = " ".join(lines[opening.line_index : opening.line_index + 2])
    return tail[:_OPENING_COUNT_LOOKAHEAD]


def _is_opening_printing_counts(
    items: list[_Item], opening: _Opening, ayes: int, noes: int
) -> bool:
    tail = _get_opening_tail(items, opening)
    ayes_match = _OPENING_AYES_COUNT_PATTERN.search(tail)
    noes_match = _OPENING_NOES_COUNT_PATTERN.search(tail)
    if ayes_match is None or noes_match is None:
        return False
    return int(ayes_match.group(1)) == ayes and int(noes_match.group(1)) == noes


def _get_division_opening(
    items: list[_Item],
    openings: list[_Opening],
    division_index: int,
    division_count: int,
    ayes: Optional[int],
    noes: Optional[int],
) -> Optional[_Opening]:
    if ayes is not None and noes is not None:
        counted_openings = [
            opening
            for opening in openings
            if _is_opening_printing_counts(items, opening, ayes, noes)
        ]
        if len(counted_openings) == 1:
            return counted_openings[0]
    if len(openings) != division_count or division_index >= len(openings):
        return None
    return openings[division_index]


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
    opening = _get_division_opening(
        items,
        _get_openings(items),
        division_index,
        division_count,
        ayes,
        noes,
    )
    if opening is None:
        return _get_unreadable_list()
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
        if printed_count is None and (
            vote_choice == DivisionVoteChoice.ABSENT
            or vote_choice == DivisionVoteChoice.PAIRED
        ):
            continue
        if vote_choice_to_name_count[vote_choice] != (printed_count or 0):
            return ParsedDivisionList(
                DivisionListStatus.COUNTS_DISAGREE, list_reading.printed_list, []
            )
    return ParsedDivisionList(
        DivisionListStatus.STORED, list_reading.printed_list, list_reading.names
    )
