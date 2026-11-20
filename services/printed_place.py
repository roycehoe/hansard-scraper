import html
import json
import re
from bisect import bisect_left
from dataclasses import dataclass
from typing import Iterable, Optional

from crud.sitting import SittingCopyRow
from enums import PrintedPlaceRule, ReportType
from schemas.hansard_report_response import HansardReportSection

_ASSENT_PLACE = 0
_RUN_WORD_COUNT = 12
_NOT_FOUND = -1
_TABLE_PATTERN = r"<table.*?</table>"
_HTML_TAG_PATTERN = r"<[^>]+>"
_NON_ALPHANUMERIC_PATTERN = r"[^a-z0-9]+"


@dataclass(frozen=True)
class PlaceableReport:
    report_id: str
    report_type: str
    speech_number: int
    original_title: str
    subtitle: Optional[str]
    content: Optional[str]


@dataclass(frozen=True)
class PrintedPlace:
    printed_place: Optional[int]
    printed_place_rule: PrintedPlaceRule


_NOT_PLACED = PrintedPlace(None, PrintedPlaceRule.NOT_PLACED)
_ASSENT_FIRST = PrintedPlace(_ASSENT_PLACE, PrintedPlaceRule.ASSENT_FIRST)


def _is_assent_without_text(placeable_report: PlaceableReport) -> bool:
    return (
        placeable_report.report_type == ReportType.ATBP
        and not (placeable_report.content or "").strip()
    )


def _get_normalized_heading(heading: Optional[str]) -> str:
    return " ".join((heading or "").lower().split())


def _get_title_place(
    sections: list[HansardReportSection],
    used_positions: set[int],
    placeable_report: PlaceableReport,
) -> PrintedPlace:
    title = _get_normalized_heading(placeable_report.original_title)
    positions = [
        position
        for position, section in enumerate(sections, start=1)
        if position not in used_positions
        and _get_normalized_heading(section.title) == title
    ]
    if len(positions) == 1:
        return PrintedPlace(positions[0], PrintedPlaceRule.SECTION_TITLE)
    if len(positions) == 0:
        return _NOT_PLACED
    subtitle = _get_normalized_heading(placeable_report.subtitle)
    subtitle_positions = [
        position
        for position in positions
        if _get_normalized_heading(sections[position - 1].sub_title) == subtitle
    ]
    if len(subtitle_positions) == 1:
        return PrintedPlace(
            subtitle_positions[0], PrintedPlaceRule.SECTION_TITLE_AND_SUBTITLE
        )
    return _NOT_PLACED


def get_newer_printed_places(
    sections: str, placeable_reports: list[PlaceableReport]
) -> dict[str, PrintedPlace]:
    hansard_report_sections = [
        HansardReportSection.model_validate(raw_section)
        for raw_section in json.loads(sections)
    ]
    content_to_positions: dict[str, list[int]] = {}
    for position, section in enumerate(hansard_report_sections, start=1):
        if section.content is None:
            continue
        content_to_positions.setdefault(section.content, []).append(position)
    ordered_reports = sorted(
        placeable_reports,
        key=lambda placeable_report: (
            placeable_report.speech_number,
            placeable_report.report_id,
        ),
    )
    report_id_to_printed_place: dict[str, PrintedPlace] = {}
    used_positions: set[int] = set()
    for placeable_report in ordered_reports:
        if _is_assent_without_text(placeable_report):
            report_id_to_printed_place[placeable_report.report_id] = _ASSENT_FIRST
            continue
        if placeable_report.content is None:
            continue
        positions = content_to_positions.get(placeable_report.content, [])
        if len(positions) != 1:
            continue
        if positions[0] in used_positions:
            continue
        report_id_to_printed_place[placeable_report.report_id] = PrintedPlace(
            positions[0], PrintedPlaceRule.SECTION_TEXT
        )
        used_positions.add(positions[0])
    for placeable_report in ordered_reports:
        if placeable_report.report_id in report_id_to_printed_place:
            continue
        title_place = _get_title_place(
            hansard_report_sections, used_positions, placeable_report
        )
        report_id_to_printed_place[placeable_report.report_id] = title_place
        if title_place.printed_place is not None:
            used_positions.add(title_place.printed_place)
    return report_id_to_printed_place


@dataclass(frozen=True)
class SittingWords:
    joined_text: str
    word_starts: list[int]


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int


def _get_words(html_text: str) -> list[str]:
    text_without_tables = re.sub(
        _TABLE_PATTERN, " ", html_text, flags=re.IGNORECASE | re.DOTALL
    )
    plain_text = html.unescape(re.sub(_HTML_TAG_PATTERN, " ", text_without_tables))
    return re.sub(_NON_ALPHANUMERIC_PATTERN, " ", plain_text.lower()).split()


def _build_sitting_words(html_full_content: str) -> SittingWords:
    words = _get_words(html_full_content)
    word_starts = []
    word_start = 1
    for word in words:
        word_starts.append(word_start)
        word_start += len(word) + 1
    return SittingWords(" " + " ".join(words) + " ", word_starts)


def _get_unique_run_place(
    sitting_words: SittingWords, run_words: list[str]
) -> Optional[int]:
    run_text = " " + " ".join(run_words) + " "
    first_hit = sitting_words.joined_text.find(run_text)
    if first_hit == _NOT_FOUND:
        return None
    if sitting_words.joined_text.find(run_text, first_hit + 1) != _NOT_FOUND:
        return None
    return bisect_left(sitting_words.word_starts, first_hit + 1)


def _get_first_unique_run_place(
    sitting_words: SittingWords,
    words: list[str],
    run_offsets: Iterable[int],
    run_word_count: int,
) -> Optional[int]:
    for run_offset in run_offsets:
        run_place = _get_unique_run_place(
            sitting_words, words[run_offset : run_offset + run_word_count]
        )
        if run_place is not None:
            return run_place
    return None


def _get_text_span(sitting_words: SittingWords, words: list[str]) -> Optional[TextSpan]:
    run_word_count = min(_RUN_WORD_COUNT, len(words))
    last_run_offset = len(words) - run_word_count
    start_place = _get_first_unique_run_place(
        sitting_words, words, range(0, last_run_offset + 1), run_word_count
    )
    if start_place is None:
        return None
    end_run_place = _get_first_unique_run_place(
        sitting_words, words, range(last_run_offset, -1, -1), run_word_count
    )
    if end_run_place is None:
        return None
    if end_run_place < start_place:
        return None
    return TextSpan(start_place, end_run_place + run_word_count)


def _get_overlapping_report_ids(
    report_id_to_text_span: dict[str, TextSpan],
) -> set[str]:
    report_ids = list(report_id_to_text_span)
    overlapping_report_ids: set[str] = set()
    for i, report_id in enumerate(report_ids):
        text_span = report_id_to_text_span[report_id]
        for other_report_id in report_ids[i + 1 :]:
            other_text_span = report_id_to_text_span[other_report_id]
            if (
                text_span.start < other_text_span.end
                and other_text_span.start < text_span.end
            ):
                overlapping_report_ids.add(report_id)
                overlapping_report_ids.add(other_report_id)
    return overlapping_report_ids


def get_older_printed_places(
    html_full_content: str, placeable_reports: list[PlaceableReport]
) -> dict[str, PrintedPlace]:
    sitting_words = _build_sitting_words(html_full_content)
    report_id_to_printed_place: dict[str, PrintedPlace] = {}
    report_id_to_text_span: dict[str, TextSpan] = {}
    for placeable_report in placeable_reports:
        if _is_assent_without_text(placeable_report):
            report_id_to_printed_place[placeable_report.report_id] = _ASSENT_FIRST
            continue
        words = _get_words(placeable_report.content or "")
        if not words:
            report_id_to_printed_place[placeable_report.report_id] = _NOT_PLACED
            continue
        text_span = _get_text_span(sitting_words, words)
        if text_span is None:
            report_id_to_printed_place[placeable_report.report_id] = _NOT_PLACED
            continue
        report_id_to_text_span[placeable_report.report_id] = text_span
    overlapping_report_ids = _get_overlapping_report_ids(report_id_to_text_span)
    for report_id, text_span in report_id_to_text_span.items():
        if report_id in overlapping_report_ids:
            report_id_to_printed_place[report_id] = _NOT_PLACED
            continue
        report_id_to_printed_place[report_id] = PrintedPlace(
            text_span.start, PrintedPlaceRule.FULL_TEXT_RUN
        )
    return report_id_to_printed_place


def get_printed_places(
    sitting_copy: Optional[SittingCopyRow], placeable_reports: list[PlaceableReport]
) -> dict[str, PrintedPlace]:
    if sitting_copy is not None:
        if sitting_copy.sections is not None:
            return get_newer_printed_places(sitting_copy.sections, placeable_reports)
        if sitting_copy.html_full_content is not None:
            return get_older_printed_places(
                sitting_copy.html_full_content, placeable_reports
            )
    return {
        placeable_report.report_id: _NOT_PLACED
        for placeable_report in placeable_reports
    }
