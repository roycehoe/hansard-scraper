import html
import re
from bisect import bisect_right
from dataclasses import dataclass
from itertools import groupby
from typing import Optional

from enums import ColumnNote, MissingColumnReason

_COLUMN_MARKER_PATTERN = r"Column(?:\s+No)?\s*:\s*(\d+)"
_MISSPELT_COLUMN_MARKER_PATTERN = r"Columnn(?:\s+No)?\s*:?\s*(\d+)\b|Column(?:\s+No)?\s*:\s*([\dl]*l[\dl]*)\b|Column(?:\s+No)?\s+(\d+)\b"
_LETTER_FOR_ONE = "l"
_HEAD_BLOCK_PATTERN = r"<head\b[^>]*>.*?</head\s*>"
_HEAD_START_COLUMN_PATTERN = r"<meta\s+name=\"Start_Col\"\s+content=\"(\d+)\""
_HEAD_END_COLUMN_PATTERN = r"<meta\s+name=\"End_Col\"\s+content=\"(\d+)\""
_HTML_TAG_PATTERN = r"<[^>]*>"
_NON_ALPHANUMERIC_PATTERN = r"[^a-z0-9]+"
_SPEECH_EDGE_LENGTH = 40
_SHORT_ROW_REACH = 200
_EVENT_OPENINGS = "[("
_MAX_COLUMN_JUMP = 50


@dataclass(frozen=True)
class PrintedColumnMarker:
    offset: int
    column: int
    is_letter_for_digit: bool


@dataclass(frozen=True)
class ColumnText:
    alphanumerics: str
    markers: tuple[PrintedColumnMarker, ...]
    misspelt_markers: tuple[PrintedColumnMarker, ...]


@dataclass(frozen=True)
class ColumnMarker:
    offset: int
    column: int
    sequence_column: int
    column_note: Optional[ColumnNote]


@dataclass(frozen=True)
class ColumnRange:
    column_start: int
    column_end: int


@dataclass(frozen=True)
class SpeechText:
    speaker: Optional[str]
    transcript: str


@dataclass(frozen=True)
class SpeechColumn:
    column_start: Optional[int]
    column_note: Optional[ColumnNote]
    column_suggested: Optional[int]
    missing_column_reason: Optional[MissingColumnReason]


@dataclass(frozen=True)
class ReportColumnRange:
    id: int
    column_start: Optional[int]
    column_end: Optional[int]


@dataclass(frozen=True)
class SpeechColumnNote:
    id: int
    column_note: Optional[ColumnNote]
    column_suggested: Optional[int]


def _get_alphanumerics(text: str) -> str:
    return re.sub(_NON_ALPHANUMERIC_PATTERN, "", text.lower())


def _get_html_alphanumerics(html_fragment: str) -> str:
    # NOTE: tags go before entities are decoded, so an escaped "&lt;b&gt;" stays text as it does in the markdown.
    return _get_alphanumerics(html.unescape(re.sub(_HTML_TAG_PATTERN, "", html_fragment)))


def _is_inside_tag(body_html: str, position: int) -> bool:
    return body_html.rfind("<", 0, position) > body_html.rfind(">", 0, position)


def _is_overlapping(match: re.Match, other_matches: list[re.Match]) -> bool:
    return any(other_match.start() < match.end() and match.start() < other_match.end() for other_match in other_matches)


def build_column_text(report_html: str) -> ColumnText:
    body_html = re.sub(_HEAD_BLOCK_PATTERN, "", report_html, flags=re.DOTALL | re.IGNORECASE)
    marker_matches = list(re.finditer(_COLUMN_MARKER_PATTERN, body_html))
    misspelt_matches = [
        match
        for match in re.finditer(_MISSPELT_COLUMN_MARKER_PATTERN, body_html)
        if not _is_inside_tag(body_html, match.start()) and not _is_overlapping(match, marker_matches)
    ]
    alphanumeric_parts = []
    markers = []
    misspelt_markers = []
    offset = 0
    fragment_start = 0
    for match, is_misspelt in sorted([(match, False) for match in marker_matches] + [(match, True) for match in misspelt_matches], key=lambda pair: pair[0].start()):
        fragment = _get_html_alphanumerics(body_html[fragment_start : match.start()])
        alphanumeric_parts.append(fragment)
        offset += len(fragment)
        if not is_misspelt:
            markers.append(PrintedColumnMarker(offset, int(match.group(1)), is_letter_for_digit=False))
            fragment_start = match.end()
            continue
        printed_column = next(group for group in match.groups() if group is not None)
        misspelt_markers.append(PrintedColumnMarker(offset, int(printed_column.replace(_LETTER_FOR_ONE, "1")), _LETTER_FOR_ONE in printed_column))
        # NOTE: the parser keeps a misspelt marker as text, so its letters stay in the text the rows are matched against.
        fragment_start = match.start()
    alphanumeric_parts.append(_get_html_alphanumerics(body_html[fragment_start:]))
    return ColumnText("".join(alphanumeric_parts), tuple(markers), tuple(misspelt_markers))


def get_head_column_range(report_html: str) -> Optional[ColumnRange]:
    start_match = re.search(_HEAD_START_COLUMN_PATTERN, report_html, flags=re.IGNORECASE)
    end_match = re.search(_HEAD_END_COLUMN_PATTERN, report_html, flags=re.IGNORECASE)
    if start_match is None:
        return None
    if end_match is None:
        return None
    # NOTE: some Parliament 11 heads print 0 for both columns.
    if int(start_match.group(1)) == 0:
        return None
    return ColumnRange(int(start_match.group(1)), int(end_match.group(1)))


def _get_misprint_suggestion(previous_column: int, column: int, following_column: int) -> Optional[int]:
    if previous_column + 2 != following_column:
        return None
    if column == previous_column + 1:
        return None
    return previous_column + 1


def _get_read_markers(markers: tuple[PrintedColumnMarker, ...]) -> list[ColumnMarker]:
    # NOTE: a marker printed twice in a row is one column, so neighbours are compared run by run.
    runs = [list(run) for _, run in groupby(markers, key=lambda marker: marker.column)]
    read_markers = []
    for i, run in enumerate(runs):
        suggested_column = None if i == 0 or i == len(runs) - 1 else _get_misprint_suggestion(runs[i - 1][0].column, run[0].column, runs[i + 1][0].column)
        for marker in run:
            if suggested_column is None:
                read_markers.append(ColumnMarker(marker.offset, marker.column, marker.column, None))
                continue
            read_markers.append(ColumnMarker(marker.offset, marker.column, suggested_column, ColumnNote.LIKELY_MISPRINT))
    return read_markers


def _is_fitting_misspelt_marker(column: int, previous_marker: Optional[ColumnMarker], following_marker: Optional[ColumnMarker]) -> bool:
    if previous_marker is None and following_marker is None:
        return False
    if previous_marker is None:
        return column == following_marker.sequence_column - 1
    if following_marker is None:
        return column == previous_marker.sequence_column + 1
    return column == previous_marker.sequence_column + 1 and column < following_marker.sequence_column


def get_column_markers(column_text: ColumnText) -> tuple[ColumnMarker, ...]:
    column_markers = _get_read_markers(column_text.markers)
    for misspelt_marker in column_text.misspelt_markers:
        insert_at = bisect_right(column_markers, misspelt_marker.offset, key=lambda column_marker: column_marker.offset)
        previous_marker = column_markers[insert_at - 1] if insert_at > 0 else None
        following_marker = column_markers[insert_at] if insert_at < len(column_markers) else None
        # NOTE: prose such as "column 5 of the table" also matches, so only a number that fills the marker sequence counts.
        if not _is_fitting_misspelt_marker(misspelt_marker.column, previous_marker, following_marker):
            continue
        column_note = ColumnNote.PRINTED_WITH_L_FOR_1 if misspelt_marker.is_letter_for_digit else None
        column_markers.insert(insert_at, ColumnMarker(misspelt_marker.offset, misspelt_marker.column, misspelt_marker.column, column_note))
    return tuple(column_markers)


def _is_broken_step(previous_column: int, column: int) -> bool:
    return column < previous_column or column - previous_column > _MAX_COLUMN_JUMP


def _get_range_start(first_marker: ColumnMarker, head_column_range: Optional[ColumnRange]) -> int:
    if head_column_range is not None and head_column_range.column_start == first_marker.sequence_column - 1:
        return head_column_range.column_start
    return first_marker.column


def _get_range_end(last_marker: ColumnMarker, head_column_range: Optional[ColumnRange]) -> int:
    if head_column_range is not None and head_column_range.column_end == last_marker.sequence_column + 1:
        return head_column_range.column_end
    return last_marker.column


def get_report_column_range(column_markers: tuple[ColumnMarker, ...], head_column_range: Optional[ColumnRange]) -> Optional[ColumnRange]:
    if not column_markers:
        return None
    for previous_marker, marker in zip(column_markers, column_markers[1:]):
        if _is_broken_step(previous_marker.sequence_column, marker.sequence_column):
            return None
    # NOTE: a head that ends more than one past the last marker leaves the end unknown, so the report gets no range.
    if head_column_range is not None and head_column_range.column_end > column_markers[-1].sequence_column + 1:
        return None
    return ColumnRange(_get_range_start(column_markers[0], head_column_range), _get_range_end(column_markers[-1], head_column_range))


def _get_marker_index(column_markers: tuple[ColumnMarker, ...], offset: int) -> int:
    return bisect_right(column_markers, offset, key=lambda column_marker: column_marker.offset) - 1


def _get_marked_column(marker: ColumnMarker, is_speaker_label: bool) -> SpeechColumn:
    if marker.column_note is not None:
        column_suggested = None if marker.sequence_column == marker.column else marker.sequence_column
        return SpeechColumn(marker.column, marker.column_note, column_suggested, None)
    if is_speaker_label:
        return SpeechColumn(marker.column, ColumnNote.SPEAKER_NAMED_IN_COLUMN_BEFORE, None, None)
    return SpeechColumn(marker.column, None, None, None)


def _get_column_before_first_marker(first_marker: ColumnMarker, head_column_range: Optional[ColumnRange], is_speaker_label: bool) -> SpeechColumn:
    if head_column_range is None:
        return SpeechColumn(None, None, None, MissingColumnReason.BEFORE_FIRST_MARKER)
    # NOTE: a head start more than one below the first marker leaves the column unknown, as a skipped marker does.
    if head_column_range.column_start != first_marker.sequence_column - 1:
        return SpeechColumn(None, None, None, MissingColumnReason.BEFORE_FIRST_MARKER)
    if is_speaker_label:
        return SpeechColumn(head_column_range.column_start, ColumnNote.SPEAKER_NAMED_IN_COLUMN_BEFORE, None, None)
    return SpeechColumn(head_column_range.column_start, None, None, None)


def _get_column_after_last_marker(column_markers: tuple[ColumnMarker, ...], marker_index: int, head_column_range: Optional[ColumnRange], is_speaker_label: bool) -> SpeechColumn:
    marker = column_markers[marker_index]
    # NOTE: the head ends past the last marker, so the text after it may sit in any column up to the head's end.
    if head_column_range is not None and head_column_range.column_end > marker.sequence_column:
        return SpeechColumn(None, None, None, MissingColumnReason.PAST_LAST_MARKER)
    preceding_marker = next((column_marker for column_marker in reversed(column_markers[:marker_index]) if column_marker.sequence_column != marker.sequence_column), None)
    # NOTE: no marker follows to confirm the last one, so a break into it leaves the column unknown.
    if preceding_marker is not None and _is_broken_step(preceding_marker.sequence_column, marker.sequence_column):
        return SpeechColumn(None, None, None, MissingColumnReason.BROKEN_SEQUENCE)
    return _get_marked_column(marker, is_speaker_label)


def _get_speech_column(column_markers: tuple[ColumnMarker, ...], head_column_range: Optional[ColumnRange], offset: int, is_speaker_label: bool) -> SpeechColumn:
    marker_index = _get_marker_index(column_markers, offset)
    if marker_index == -1:
        return _get_column_before_first_marker(column_markers[0], head_column_range, is_speaker_label)
    marker = column_markers[marker_index]
    following_marker = next((column_marker for column_marker in column_markers[marker_index + 1 :] if column_marker.sequence_column != marker.sequence_column), None)
    if following_marker is None:
        return _get_column_after_last_marker(column_markers, marker_index, head_column_range, is_speaker_label)
    if following_marker.sequence_column == marker.sequence_column + 1:
        return _get_marked_column(marker, is_speaker_label)
    if _is_broken_step(marker.sequence_column, following_marker.sequence_column):
        return SpeechColumn(None, None, None, MissingColumnReason.BROKEN_SEQUENCE)
    return SpeechColumn(None, None, None, MissingColumnReason.SKIPPED_COLUMN)


def _get_label_start(alphanumerics: str, column_markers: tuple[ColumnMarker, ...], speaker: Optional[str], speech_start: int, label_floor: int) -> Optional[int]:
    label = _get_alphanumerics(speaker or "")
    label_start = speech_start - len(label)
    if not label:
        return None
    # NOTE: a label before the previous row's last words belongs to another row.
    if label_start < label_floor:
        return None
    if not alphanumerics.startswith(label, label_start):
        return None
    if _get_marker_index(column_markers, label_start) == _get_marker_index(column_markers, speech_start):
        return None
    return label_start


def _get_found_speech_column(
    column_text: ColumnText,
    column_markers: tuple[ColumnMarker, ...],
    head_column_range: Optional[ColumnRange],
    speech_text: SpeechText,
    speech_start: int,
    label_floor: int,
) -> SpeechColumn:
    label_start = _get_label_start(column_text.alphanumerics, column_markers, speech_text.speaker, speech_start, label_floor)
    if label_start is None:
        return _get_speech_column(column_markers, head_column_range, speech_start, is_speaker_label=False)
    # NOTE: a speech is cited where its speaker is named, so a label printed before a marker takes the column it is printed in.
    return _get_speech_column(column_markers, head_column_range, label_start, is_speaker_label=True)


def _get_long_row_start(alphanumerics: str, speech_opening: str, search_offset: int, previous_start: int) -> int:
    speech_start = alphanumerics.find(speech_opening, search_offset)
    if speech_start != -1:
        return speech_start
    # NOTE: a long event the parser moves out of a paragraph also sits inside the row before.
    return alphanumerics.find(speech_opening, previous_start + 1)


def _get_leading_speech_columns(column_text: ColumnText, first_marker: ColumnMarker, head_column_range: Optional[ColumnRange], speech_texts: list[SpeechText]) -> list[SpeechColumn]:
    leading_speech_columns = []
    search_offset = 0
    for speech_text in speech_texts:
        speech_opening = _get_alphanumerics(speech_text.transcript)[:_SPEECH_EDGE_LENGTH]
        if not speech_opening:
            break
        speech_start = column_text.alphanumerics.find(speech_opening, search_offset, first_marker.offset)
        if speech_start == -1:
            break
        leading_speech_columns.append(_get_column_before_first_marker(first_marker, head_column_range, is_speaker_label=False))
        search_offset = speech_start + len(speech_opening)
    return leading_speech_columns


def get_speech_columns(
    column_text: ColumnText,
    column_markers: tuple[ColumnMarker, ...],
    head_column_range: Optional[ColumnRange],
    speech_texts: list[SpeechText],
) -> list[SpeechColumn]:
    if not column_markers:
        return [SpeechColumn(None, None, None, MissingColumnReason.NO_MARKERS)] * len(speech_texts)
    speech_columns = []
    # NOTE: the header before the first marker would use up a short row's reach, so the search starts at that marker.
    search_offset = column_markers[0].offset
    previous_start = search_offset - 1
    event_floor = search_offset
    label_floor = 0
    for speech_text in speech_texts:
        transcript_alphanumerics = _get_alphanumerics(speech_text.transcript)
        if not transcript_alphanumerics:
            speech_columns.append(SpeechColumn(None, None, None, MissingColumnReason.TEXT_NOT_FOUND))
            continue
        # NOTE: a short row such as "[Laughter]" also matches far ahead, so it is looked for only near the search point.
        if len(transcript_alphanumerics) < _SPEECH_EDGE_LENGTH:
            # NOTE: the parser puts the events it cuts from a paragraph right after its row, in order, so an event row is matched inside that row first.
            is_event = speech_text.transcript.lstrip()[:1] in _EVENT_OPENINGS
            event_start = column_text.alphanumerics.find(transcript_alphanumerics, event_floor, search_offset) if is_event else -1
            if event_start != -1:
                speech_columns.append(_get_speech_column(column_markers, head_column_range, event_start, is_speaker_label=False))
                event_floor = event_start + len(transcript_alphanumerics)
                continue
            reach_end = search_offset + _SHORT_ROW_REACH + len(transcript_alphanumerics)
            speech_start = column_text.alphanumerics.find(transcript_alphanumerics, search_offset, reach_end)
            if speech_start != -1:
                speech_columns.append(_get_found_speech_column(column_text, column_markers, head_column_range, speech_text, speech_start, label_floor))
                search_offset = speech_start + len(transcript_alphanumerics)
                event_floor = search_offset
                label_floor = search_offset
                continue
            # NOTE: the parser moves a gesture or an event cut from inside a paragraph to a row after it, so such a row sits inside the row before.
            speech_start = column_text.alphanumerics.find(transcript_alphanumerics, previous_start + 1, search_offset)
            if speech_start == -1:
                speech_columns.append(SpeechColumn(None, None, None, MissingColumnReason.TEXT_NOT_FOUND))
                continue
            speech_columns.append(_get_speech_column(column_markers, head_column_range, speech_start, is_speaker_label=False))
            continue
        speech_opening = transcript_alphanumerics[:_SPEECH_EDGE_LENGTH]
        speech_start = _get_long_row_start(column_text.alphanumerics, speech_opening, search_offset, previous_start)
        if speech_start == -1:
            speech_columns.append(SpeechColumn(None, None, None, MissingColumnReason.TEXT_NOT_FOUND))
            continue
        speech_columns.append(_get_found_speech_column(column_text, column_markers, head_column_range, speech_text, speech_start, label_floor))
        previous_start = speech_start
        event_floor = speech_start + 1
        speech_closing = transcript_alphanumerics[-_SPEECH_EDGE_LENGTH:]
        # NOTE: the next row is looked for after this row's last words, so a short row such as "Yes." cannot match inside the row before it.
        speech_closing_start = column_text.alphanumerics.find(speech_closing, speech_start)
        if speech_closing_start == -1:
            search_offset = speech_start + len(speech_opening)
            label_floor = search_offset
            continue
        search_offset = speech_closing_start + len(speech_closing)
        label_floor = search_offset
    found_index = next((i for i, speech_column in enumerate(speech_columns) if speech_column.missing_column_reason != MissingColumnReason.TEXT_NOT_FOUND), len(speech_columns))
    # NOTE: rows before the first marker are looked for only before the first row found after it, and only there.
    leading_speech_columns = _get_leading_speech_columns(column_text, column_markers[0], head_column_range, speech_texts[:found_index])
    return leading_speech_columns + speech_columns[len(leading_speech_columns) :]
