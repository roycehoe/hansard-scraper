import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from sqlmodel import Session

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.report import CRUDReport
from crud.speech import CRUDSpeech, SpeechRow
from database.init import engine
from database.report import Report
from logs import logger
from utils.column_numbers import (
    ColumnRange,
    build_column_text,
    get_report_column_range,
    get_speech_start_columns,
)

_REPORT_BATCH = 200
_HEAD_START_COLUMN_PATTERN = r"<meta\s+name=\"Start_Col\"\s+content=\"(\d+)\""
_HEAD_END_COLUMN_PATTERN = r"<meta\s+name=\"End_Col\"\s+content=\"(\d+)\""
_SAMPLE_REPORT_COUNT = 10


@dataclass
class ColumnCoverageTally:
    reports: int = 0
    reports_with_markers: int = 0
    markers: int = 0
    reports_with_markers_out_of_order: int = 0
    reports_with_head_range: int = 0
    reports_with_head_range_equal: int = 0
    rows: int = 0
    rows_in_reports_with_markers: int = 0
    rows_with_column: int = 0
    rows_back_a_column: int = 0
    rows_outside_head_range: int = 0


def _get_head_column_range(content: str) -> Optional[ColumnRange]:
    start_match = re.search(_HEAD_START_COLUMN_PATTERN, content, flags=re.IGNORECASE)
    end_match = re.search(_HEAD_END_COLUMN_PATTERN, content, flags=re.IGNORECASE)
    if start_match is None:
        return None
    if end_match is None:
        return None
    # NOTE: some Parliament 11 heads print 0 for both columns.
    if int(start_match.group(1)) == 0:
        return None
    return ColumnRange(int(start_match.group(1)), int(end_match.group(1)))


def _tally_report(tally: ColumnCoverageTally, report: Report, speech_rows: list[SpeechRow]) -> int:
    tally.reports += 1
    tally.rows += len(speech_rows)
    column_text = build_column_text(report.content or "")
    column_range = get_report_column_range(column_text)
    if column_range is None:
        return 0
    marker_columns = [marker.column for marker in column_text.markers]
    tally.reports_with_markers += 1
    tally.markers += len(marker_columns)
    tally.reports_with_markers_out_of_order += marker_columns != sorted(marker_columns)
    tally.rows_in_reports_with_markers += len(speech_rows)
    head_column_range = _get_head_column_range(report.content or "")
    if head_column_range is not None:
        tally.reports_with_head_range += 1
        tally.reports_with_head_range_equal += head_column_range == column_range
    start_columns = [column for column in get_speech_start_columns(column_text, [speech_row.transcript for speech_row in speech_rows]) if column is not None]
    tally.rows_with_column += len(start_columns)
    tally.rows_back_a_column += sum(after < before for before, after in zip(start_columns, start_columns[1:]))
    if head_column_range is not None:
        tally.rows_outside_head_range += sum(
            column < head_column_range.column_start or column > head_column_range.column_end for column in start_columns
        )
    return len(speech_rows) - len(start_columns)


def _get_share(part: int, whole: int) -> str:
    if whole == 0:
        return "-"
    return f"{part / whole:.1%}"


def count_column_coverage() -> None:
    group_to_tally: defaultdict[tuple[str, int], ColumnCoverageTally] = defaultdict(ColumnCoverageTally)
    rows_without_column_by_report = []
    with Session(engine) as session:
        report_ids = sorted(report_header_row.id for report_header_row in CRUDReport(session).get_header_rows())
        for start in range(0, len(report_ids), _REPORT_BATCH):
            batch_report_ids = report_ids[start:start + _REPORT_BATCH]
            report_id_to_speech_rows = defaultdict(list)
            for speech_row in CRUDSpeech(session).get_rows_by_report_ids(batch_report_ids):
                report_id_to_speech_rows[speech_row.report_id].append(speech_row)
            for report in CRUDReport(session).get_by_ids(batch_report_ids):
                tally = group_to_tally[(report.report_version, report.parliament_number)]
                rows_without_column = _tally_report(tally, report, report_id_to_speech_rows[report.id])
                rows_without_column_by_report.append((rows_without_column, report.id))
            session.expunge_all()
    for (report_version, parliament_number), tally in sorted(group_to_tally.items()):
        logger.info(
            f"{report_version} Parliament {parliament_number}: {tally.reports:,} reports, {tally.reports_with_markers:,} with column markers"
            f" ({_get_share(tally.reports_with_markers, tally.reports)}), {tally.markers:,} markers,"
            f" {tally.reports_with_markers_out_of_order:,} with markers out of order;"
            f" {tally.reports_with_head_range:,} with a head range, {tally.reports_with_head_range_equal:,} equal to the marker range;"
            f" {tally.rows:,} rows, {tally.rows_in_reports_with_markers:,} in reports with markers,"
            f" {tally.rows_with_column:,} with a start column ({_get_share(tally.rows_with_column, tally.rows_in_reports_with_markers)} of those),"
            f" {tally.rows_back_a_column:,} back a column, {tally.rows_outside_head_range:,} outside the head range"
        )
    reports = sum(tally.reports for tally in group_to_tally.values())
    reports_with_markers = sum(tally.reports_with_markers for tally in group_to_tally.values())
    rows_in_reports_with_markers = sum(tally.rows_in_reports_with_markers for tally in group_to_tally.values())
    rows_with_column = sum(tally.rows_with_column for tally in group_to_tally.values())
    logger.info(
        f"All: {reports_with_markers:,} of {reports:,} reports have column markers ({_get_share(reports_with_markers, reports)});"
        f" {rows_with_column:,} of their {rows_in_reports_with_markers:,} rows have a start column ({_get_share(rows_with_column, rows_in_reports_with_markers)})"
    )
    sample = sorted(rows_without_column_by_report, reverse=True)[:_SAMPLE_REPORT_COUNT]
    logger.info(f"Reports with the most rows without a column: {', '.join(f'{report_id} ({rows_without_column})' for rows_without_column, report_id in sample)}")


if __name__ == "__main__":
    count_column_coverage()
