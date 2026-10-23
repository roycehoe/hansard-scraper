import html
import re
from bisect import bisect_right
from dataclasses import dataclass
from typing import Optional

_COLUMN_MARKER_PATTERN = r"Column(?:\s+No)?\s*:\s*(\d+)"
_HEAD_BLOCK_PATTERN = r"<head\b[^>]*>.*?</head\s*>"
_HTML_TAG_PATTERN = r"<[^>]*>"
_NON_ALPHANUMERIC_PATTERN = r"[^a-z0-9]+"
_SPEECH_EDGE_LENGTH = 40
_SHORT_ROW_REACH = 200


@dataclass(frozen=True)
class ColumnMarker:
    offset: int
    column: int


@dataclass(frozen=True)
class ColumnText:
    alphanumerics: str
    markers: tuple[ColumnMarker, ...]


@dataclass(frozen=True)
class ColumnRange:
    column_start: int
    column_end: int


def _get_alphanumerics(text: str) -> str:
    return re.sub(_NON_ALPHANUMERIC_PATTERN, "", text.lower())


def _get_html_alphanumerics(html_fragment: str) -> str:
    # NOTE: tags go before entities are decoded, so an escaped "&lt;b&gt;" stays text as it does in the markdown.
    return _get_alphanumerics(html.unescape(re.sub(_HTML_TAG_PATTERN, "", html_fragment)))


def build_column_text(report_html: str) -> ColumnText:
    body_html = re.sub(_HEAD_BLOCK_PATTERN, "", report_html, flags=re.DOTALL | re.IGNORECASE)
    alphanumeric_parts = []
    markers = []
    offset = 0
    fragment_start = 0
    for match in re.finditer(_COLUMN_MARKER_PATTERN, body_html):
        fragment = _get_html_alphanumerics(body_html[fragment_start : match.start()])
        alphanumeric_parts.append(fragment)
        offset += len(fragment)
        markers.append(ColumnMarker(offset, int(match.group(1))))
        fragment_start = match.end()
    alphanumeric_parts.append(_get_html_alphanumerics(body_html[fragment_start:]))
    return ColumnText("".join(alphanumeric_parts), tuple(markers))


def get_report_column_range(column_text: ColumnText) -> Optional[ColumnRange]:
    if not column_text.markers:
        return None
    return ColumnRange(column_text.markers[0].column, column_text.markers[-1].column)


def _get_column_at(markers: tuple[ColumnMarker, ...], offset: int) -> int:
    return markers[bisect_right(markers, offset, key=lambda marker: marker.offset) - 1].column


def _get_long_row_start(alphanumerics: str, speech_opening: str, search_offset: int, previous_start: int) -> int:
    speech_start = alphanumerics.find(speech_opening, search_offset)
    if speech_start != -1:
        return speech_start
    # NOTE: a long event the parser moves out of a paragraph also sits inside the row before.
    return alphanumerics.find(speech_opening, previous_start + 1)


def get_speech_start_columns(column_text: ColumnText, transcripts: list[str]) -> list[Optional[int]]:
    if not column_text.markers:
        return [None] * len(transcripts)
    start_columns = []
    # NOTE: text before the first marker sits in a column the report never prints, so the search starts at that marker.
    search_offset = column_text.markers[0].offset
    previous_start = search_offset - 1
    for transcript in transcripts:
        transcript_alphanumerics = _get_alphanumerics(transcript)
        if not transcript_alphanumerics:
            start_columns.append(None)
            continue
        # NOTE: a short row such as "[Laughter]" also matches far ahead, so it is looked for only near the search point.
        if len(transcript_alphanumerics) < _SPEECH_EDGE_LENGTH:
            reach_end = search_offset + _SHORT_ROW_REACH + len(transcript_alphanumerics)
            speech_start = column_text.alphanumerics.find(transcript_alphanumerics, search_offset, reach_end)
            if speech_start != -1:
                start_columns.append(_get_column_at(column_text.markers, speech_start))
                search_offset = speech_start + len(transcript_alphanumerics)
                continue
            # NOTE: the parser moves a gesture or an event cut from inside a paragraph to a row after it, so such a row sits inside the row before.
            speech_start = column_text.alphanumerics.find(transcript_alphanumerics, previous_start + 1, search_offset)
            start_columns.append(None if speech_start == -1 else _get_column_at(column_text.markers, speech_start))
            continue
        speech_opening = transcript_alphanumerics[:_SPEECH_EDGE_LENGTH]
        speech_start = _get_long_row_start(column_text.alphanumerics, speech_opening, search_offset, previous_start)
        if speech_start == -1:
            start_columns.append(None)
            continue
        start_columns.append(_get_column_at(column_text.markers, speech_start))
        previous_start = speech_start
        speech_closing = transcript_alphanumerics[-_SPEECH_EDGE_LENGTH:]
        # NOTE: the next row is looked for after this row's last words, so a short row such as "Yes." cannot match inside the row before it.
        speech_closing_start = column_text.alphanumerics.find(speech_closing, speech_start)
        if speech_closing_start == -1:
            search_offset = speech_start + len(speech_opening)
            continue
        search_offset = speech_closing_start + len(speech_closing)
    return start_columns
