import json
from dataclasses import dataclass
from typing import Optional

from enums import PrintedPlaceRule, ReportType
from schemas.hansard_report_response import HansardReportSection

_ASSENT_PLACE = 0


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
    return placeable_report.report_type == ReportType.ATBP and not (
        placeable_report.content or ""
    ).strip()


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
