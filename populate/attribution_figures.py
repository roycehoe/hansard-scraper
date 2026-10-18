import re
from collections import Counter, defaultdict

from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.report import Report
from services.attribution import (
    HEADLINE_GROUP,
    HEADLINE_MAX_PARLIAMENT,
    AttributionFigures,
    GroupFigures,
    ReportTypeFigures,
    get_countable_character_count,
    get_group,
    get_speech_category,
)
from services.speech import (
    _REPORT_HEADER_FIELD_RE,
    _is_artifact_line,
    get_fallback_speaker,
    get_start_of_speech_line,
)

_REPORT_BATCH = 2_000
_HEADER_SCAN_LINE_COUNT = 15
_NO_HEADER_ROW_INDEX = -1
_RULE_LINE_PREFIX = "---"

_LEADING_BOLD_LABEL_RE = re.compile(r"^.*?(\*\*[^*]+?\*\*\s*)+:?")
_HEADER_ROW_MARKERS = ("Title:|", "MPs Speaking:|")


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
        total += get_countable_character_count(_LEADING_BOLD_LABEL_RE.sub("", stripped, count=1) if "**" in stripped else stripped)
    return total


def _is_single_speaker_collapse(report: Report) -> bool:
    start_of_speech_line = get_start_of_speech_line(
        report.markdown_content, report.title, report.subtitle, report.original_title, report.report_type,
        report.report_version,
    )
    if start_of_speech_line is None:
        return False
    return get_fallback_speaker(report.markdown_content, start_of_speech_line, report.report_type, report.report_version) is not None


def get_attribution_figures(session: Session) -> AttributionFigures:
    report_ids = CRUDReport(session).get_ids_by_markdown_content_not_null()
    reported_parliaments: set[int] = set()
    group_to_row_count: defaultdict[str, Counter[str]] = defaultdict(Counter)
    group_to_character_count: defaultdict[str, Counter[str]] = defaultdict(Counter)
    group_and_type_to_figures: defaultdict[tuple[str, str], ReportTypeFigures] = defaultdict(ReportTypeFigures)
    reports_with_rows = set()
    group_to_body_total: Counter[str] = Counter()
    group_to_body_in_zero_row_reports: Counter[str] = Counter()
    group_to_report_ids: defaultdict[str, set] = defaultdict(set)
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch_report_ids = report_ids[start:start + _REPORT_BATCH]
        reports = CRUDReport(session).get_by_ids(batch_report_ids)
        reported_parliaments.update(report.parliament_number for report in reports if report.parliament_number > HEADLINE_MAX_PARLIAMENT)
        report_id_to_group = {report.id: get_group(report.parliament_number) for report in reports}
        report_id_to_group_and_type = {report.id: (report_id_to_group[report.id], report.report_type) for report in reports}
        for speech_row in CRUDSpeech(session).get_rows_by_report_ids(batch_report_ids):
            reports_with_rows.add(speech_row.report_id)
            category = get_speech_category(speech_row.speaker, speech_row.speaker_id)
            character_count = get_countable_character_count(speech_row.transcript)
            group = report_id_to_group[speech_row.report_id]
            group_to_row_count[group][category] += 1
            group_to_character_count[group][category] += character_count
            figures = group_and_type_to_figures[report_id_to_group_and_type[speech_row.report_id]]
            figures.category_to_row_count[category] += 1
            figures.category_to_character_count[category] += character_count

        for report in reports:
            body_character_count = _get_body_character_count(report)
            group = report_id_to_group[report.id]
            figures = group_and_type_to_figures[report_id_to_group_and_type[report.id]]
            group_to_body_total[group] += body_character_count
            group_to_report_ids[group].add(report.id)
            figures.report_count += 1
            figures.body_total += body_character_count
            if report.id not in reports_with_rows:
                group_to_body_in_zero_row_reports[group] += body_character_count
                figures.zero_row_report_count += 1
            if _is_single_speaker_collapse(report):
                figures.collapse_report_count += 1
                figures.collapse_character_count += body_character_count

    return AttributionFigures(groups=[
        GroupFigures(
            group=group,
            report_count=len(group_to_report_ids[group]),
            reports_with_rows_count=len(reports_with_rows & group_to_report_ids[group]),
            category_to_row_count=group_to_row_count[group],
            category_to_character_count=group_to_character_count[group],
            body_total=group_to_body_total[group],
            body_in_zero_row_reports=group_to_body_in_zero_row_reports[group],
            report_type_to_figures={
                report_type: figures for (group_name, report_type), figures in group_and_type_to_figures.items() if group_name == group
            },
        )
        for group in (HEADLINE_GROUP, *(get_group(parliament_number) for parliament_number in sorted(reported_parliaments)))
    ])
