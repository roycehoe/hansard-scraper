import argparse
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech, SpeechRow
from database.init import engine
from database.report import Report
from enums import ReportType
from logs import logger
from services.speech import (
    _REPORT_HEADER_FIELD_RE,
    ParsedSpeechType,
    _classify_speech_type,
    _extract_body_attribution,
    _extract_mps_speaking,
    _is_artifact_line,
    _is_section_header_speaker,
    _parse_speeches,
    get_start_of_speech_line,
)
from utils.markdown_parser import PROC_TEXT_CLOSE_TAG, PROC_TEXT_OPEN_TAG

_HEADLINE_MAX_PARLIAMENT = 11
_REPORTED_PARLIAMENTS = (12, 13, 14)
_HEADLINE_GROUP = f"Parliaments 0 to {_HEADLINE_MAX_PARLIAMENT}"
_REPORT_BATCH = 2_000
_HEADER_SCAN_LINE_COUNT = 15
_NO_HEADER_ROW_INDEX = -1
_PERCENT = 100
_RULE_LINE_PREFIX = "---"

_ADR_EXCLUDED_SPEAKER_RE = re.compile(r"hon\.? members?", re.IGNORECASE)
_MARKUP_AND_SPACE_RE = re.compile(r"[\s*_\\#|]+")
_PROC_TEXT_TAG_RE = re.compile(re.escape(PROC_TEXT_OPEN_TAG) + "|" + re.escape(PROC_TEXT_CLOSE_TAG))
_LEADING_BOLD_LABEL_RE = re.compile(r"^.*?(\*\*[^*]+?\*\*\s*)+:?")
_HEADER_ROW_MARKERS = ("Title:|", "MPs Speaking:|")
_NO_DENOMINATOR = "n/a"


@dataclass
class _GroupTypeFigures:
    report_count: int = 0
    zero_row_report_count: int = 0
    collapse_report_count: int = 0
    collapse_character_count: int = 0
    body_total: int = 0
    category_to_row_count: Counter[str] = field(default_factory=Counter)
    category_to_character_count: Counter[str] = field(default_factory=Counter)


def _get_countable_character_count(text: str) -> int:
    return len(_MARKUP_AND_SPACE_RE.sub("", _PROC_TEXT_TAG_RE.sub("", text)))


def _is_adr_excluded(speaker: str) -> bool:
    return bool(_ADR_EXCLUDED_SPEAKER_RE.search(speaker)) or speaker.startswith(("(", "_"))


def _get_body_character_count(report: Report) -> int:
    lines = report.markdown_content.splitlines()
    start = get_start_of_speech_line(
        report.markdown_content, report.title, report.subtitle, report.original_title, report.report_type,
        report.report_version,
    )
    if start is None:
        start = max((line_index for line_index, line in enumerate(lines[:_HEADER_SCAN_LINE_COUNT]) if any(marker in line for marker in _HEADER_ROW_MARKERS)), default=_NO_HEADER_ROW_INDEX)
    total = 0
    for line in lines[start + 1:]:
        stripped = line.strip()
        if _is_artifact_line(stripped) or stripped.startswith(_RULE_LINE_PREFIX) or _REPORT_HEADER_FIELD_RE.match(stripped):
            continue
        total += _get_countable_character_count(_LEADING_BOLD_LABEL_RE.sub("", stripped, count=1) if "**" in stripped else stripped)
    return total


def _is_single_speaker_collapse(report: Report) -> bool:
    start = get_start_of_speech_line(
        report.markdown_content, report.title, report.subtitle, report.original_title, report.report_type,
        report.report_version,
    )
    if start is None:
        return False
    parsed_speeches = _parse_speeches(report.markdown_content, start, report.report_type)
    speakers = _extract_mps_speaking(report.markdown_content)
    speech_type = _classify_speech_type(parsed_speeches, len(speakers))
    if speech_type == ParsedSpeechType.SINGLE_SPEAKER:
        return True
    if speech_type == ParsedSpeechType.NO_SPEAKER:
        return bool(_extract_body_attribution(report.markdown_content, report.report_type, report.report_version))
    if speech_type == ParsedSpeechType.PARSED:
        first_speaker = next((speech.speaker for speech in parsed_speeches if speech.speaker is not None), None)
        return ((report.report_type == ReportType.PRESIDENT_ADDRESS or report.report_type == ReportType.ATBP)
                and not speakers
                and first_speaker is not None
                and _is_section_header_speaker(first_speaker)
                and bool(_extract_body_attribution(report.markdown_content, report.report_type, report.report_version)))
    return False


def _get_group(parliament_number: int) -> str:
    if parliament_number <= _HEADLINE_MAX_PARLIAMENT:
        return _HEADLINE_GROUP
    return f"Parliament {parliament_number}"


def _get_category(speech_row: SpeechRow) -> str:
    if speech_row.speaker is None:
        return "no_speaker"
    if _is_adr_excluded(speech_row.speaker):
        return "adr_excluded"
    if speech_row.speaker_id is None:
        return "named_unlinked"
    return "linked"


def _get_share(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return f"{numerator} / {denominator} = {_NO_DENOMINATOR}"
    return f"{numerator} / {denominator} = {_PERCENT * numerator / denominator:.2f}%"


def _log_report_type_figures(report_type: str, figures: _GroupTypeFigures) -> None:
    linked_row_count = figures.category_to_row_count["linked"]
    adr_denominator = linked_row_count + figures.category_to_row_count["named_unlinked"]
    reports_with_rows = figures.report_count - figures.zero_row_report_count
    logger.info(f"  {report_type}: {figures.report_count} reports")
    logger.info(f"    1. ADR 0001 rate:  {_get_share(linked_row_count, adr_denominator)}")
    logger.info(f"    2. All-rows rate:  {_get_share(linked_row_count, sum(figures.category_to_row_count.values()))}")
    logger.info(f"    3. Text share:     {_get_share(figures.category_to_character_count['linked'], figures.body_total)} chars")
    logger.info(f"    Zero-row reports:  {_get_share(figures.zero_row_report_count, figures.report_count)}")
    logger.info(f"    Single-speaker collapses, reports: {_get_share(figures.collapse_report_count, reports_with_rows)}")
    logger.info(f"    Single-speaker collapses, body chars: {_get_share(figures.collapse_character_count, figures.body_total)}")


def _log_rates(category_to_row_count: Counter[str], category_to_character_count: Counter[str], body_total: int) -> None:
    rows_total = sum(category_to_row_count.values())
    adr_denominator = category_to_row_count["linked"] + category_to_row_count["named_unlinked"]
    logger.info(f"1. ADR 0001 rate:  {category_to_row_count['linked']} / {adr_denominator} = "
          f"{_PERCENT * category_to_row_count['linked'] / adr_denominator:.2f}%")
    logger.info(f"2. All-rows rate:  {category_to_row_count['linked']} / {rows_total} = {_PERCENT * category_to_row_count['linked'] / rows_total:.2f}%")
    logger.info(f"3. Text share:     {category_to_character_count['linked']} / {body_total} chars = {_PERCENT * category_to_character_count['linked'] / body_total:.2f}%")


def main(output_path: Optional[Path]) -> None:
    if output_path is not None:
        logger.add(output_path, format="{message}", mode="w")
    with Session(engine) as session:
        reports = [report for report in CRUDReport(session).get_by_markdown_content_not_null() if report.parliament_number <= _REPORTED_PARLIAMENTS[-1]]
        rows = []
        report_ids = [report.id for report in reports]
        for start in range(0, len(report_ids), _REPORT_BATCH):
            rows.extend(CRUDSpeech(session).get_rows_by_report_ids(report_ids[start:start + _REPORT_BATCH]))

    report_id_to_group = {report.id: _get_group(report.parliament_number) for report in reports}
    group_to_row_count: defaultdict[str, Counter[str]] = defaultdict(Counter)
    group_to_character_count: defaultdict[str, Counter[str]] = defaultdict(Counter)
    group_and_type_to_figures: defaultdict[tuple[str, str], _GroupTypeFigures] = defaultdict(_GroupTypeFigures)
    report_id_to_group_and_type = {report.id: (report_id_to_group[report.id], report.report_type) for report in reports}
    reports_with_rows = set()
    for row in rows:
        reports_with_rows.add(row.report_id)
        category = _get_category(row)
        character_count = _get_countable_character_count(row.transcript)
        group_to_row_count[report_id_to_group[row.report_id]][category] += 1
        group_to_character_count[report_id_to_group[row.report_id]][category] += character_count
        figures = group_and_type_to_figures[report_id_to_group_and_type[row.report_id]]
        figures.category_to_row_count[category] += 1
        figures.category_to_character_count[category] += character_count

    group_to_body_total: Counter[str] = Counter()
    body_in_zero_row_reports = 0
    for report in reports:
        body_character_count = _get_body_character_count(report)
        group_to_body_total[report_id_to_group[report.id]] += body_character_count
        if report_id_to_group[report.id] == _HEADLINE_GROUP and report.id not in reports_with_rows:
            body_in_zero_row_reports += body_character_count
        figures = group_and_type_to_figures[report_id_to_group_and_type[report.id]]
        figures.report_count += 1
        figures.body_total += body_character_count
        if report.id not in reports_with_rows:
            figures.zero_row_report_count += 1
        if _is_single_speaker_collapse(report):
            figures.collapse_report_count += 1
            figures.collapse_character_count += body_character_count

    category_to_row_count = group_to_row_count[_HEADLINE_GROUP]
    category_to_character_count = group_to_character_count[_HEADLINE_GROUP]
    body_total = group_to_body_total[_HEADLINE_GROUP]
    headline_report_ids = {report.id for report in reports if report_id_to_group[report.id] == _HEADLINE_GROUP}
    stored_character_count = sum(category_to_character_count.values())

    logger.info(f"{_HEADLINE_GROUP}: {len(headline_report_ids)} reports with markdown, "
          f"{len(reports_with_rows & headline_report_ids)} with speech rows, {sum(category_to_row_count.values())} speech rows")
    _log_rates(category_to_row_count, category_to_character_count, body_total)
    logger.info("Where the body text goes (chars, share of body):")
    for label, character_count in (
        ("linked rows", category_to_character_count["linked"]),
        ("named but unlinked rows", category_to_character_count["named_unlinked"]),
        ("ADR-excluded rows (hon. Members, stage directions)", category_to_character_count["adr_excluded"]),
        ("rows with no speaker", category_to_character_count["no_speaker"]),
        ("reports with no rows", body_in_zero_row_reports),
        ("dropped inside reports with rows (preamble, headings, labels)",
         body_total - stored_character_count - body_in_zero_row_reports),
    ):
        logger.info(f"  {label:<64} {character_count:>12} {_PERCENT * character_count / body_total:6.2f}%")
    logger.info(f"Rows by category: {dict(category_to_row_count)}")
    for parliament_number in _REPORTED_PARLIAMENTS:
        group = _get_group(parliament_number)
        logger.info(f"{group}, beside the headline:")
        _log_rates(group_to_row_count[group], group_to_character_count[group], group_to_body_total[group])

    for group in (_HEADLINE_GROUP, *(_get_group(parliament_number) for parliament_number in _REPORTED_PARLIAMENTS)):
        logger.info(f"{group}, by report type:")
        for report_type in sorted(report_type for group_name, report_type in group_and_type_to_figures if group_name == group):
            _log_report_type_figures(report_type, group_and_type_to_figures[(group, report_type)])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The three attribution numbers, by Parliament group and by report type")
    parser.add_argument("--output", type=Path, help="also write the log lines to this file, such as docs/figures/2026-10-17-round8.txt")
    main(parser.parse_args().output)
