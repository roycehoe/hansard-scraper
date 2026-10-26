import argparse
import difflib
import re
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import partial
from multiprocessing import Pool
from pathlib import Path
from typing import Optional

from sqlmodel import Session

import database.speaker  # noqa: F401 registers Speaker so the speech.speaker_id foreign key resolves
from crud.report import CRUDReport
from crud.speech import CRUDSpeech, SpeechParseRow
from database.init import engine
from database.report import Report
from logs import logger
from schemas.fresh_parse_plan import HeldReports
from schemas.fresh_vs_stored_report import (
    ComparedSpeechRow,
    DifferingBlock,
    FreshVsStoredReport,
    FreshVsStoredReports,
    FreshVsStoredStatus,
    RowDifferences,
)
from schemas.unattributed_speech import UnattributedSpeechRange
from services.speech import (
    apply_unattributed_speech_range,
    get_speeches,
    get_start_of_speech_line,
)
from utils.data_files import get_unattributed_speech_ranges
from utils.markdown_parser import get_cleaned_report_markdown

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_REPORT_BATCH = 100
_WORKER_COUNT = 2
_TASKS_PER_WORKER = 25
_PROGRESS_EVERY = 2_000
_TRACEBACK_LIMIT = 4
_EQUAL_OPCODE = "equal"
_READ_ONLY_ENGINE = engine.execution_options(postgresql_readonly=True)


@dataclass(frozen=True)
class _FreshParse:
    markdown: Optional[str]
    rows: Optional[list[ComparedSpeechRow]]


def tokenize(text: str) -> Counter[str]:
    return Counter(_TOKEN_RE.findall(text.lower()))


def _count_row_tokens(rows: list[ComparedSpeechRow]) -> Counter[str]:
    token_counts: Counter[str] = Counter()
    for compared_row in rows:
        token_counts.update(tokenize(compared_row.transcript))
    return token_counts


def compare_rows(stored_rows: list[ComparedSpeechRow], stored_ordinals: list[int], fresh_rows: list[ComparedSpeechRow]) -> FreshVsStoredStatus:
    if stored_rows != fresh_rows:
        return FreshVsStoredStatus.CONTENT
    if stored_ordinals != list(range(1, len(fresh_rows) + 1)):
        return FreshVsStoredStatus.ORDINAL_ONLY
    return FreshVsStoredStatus.SAME


def get_row_differences(stored_rows: list[ComparedSpeechRow], fresh_rows: list[ComparedSpeechRow]) -> RowDifferences:
    stored_tokens = _count_row_tokens(stored_rows)
    fresh_tokens = _count_row_tokens(fresh_rows)
    tokens_lost = stored_tokens - fresh_tokens
    tokens_gained = fresh_tokens - stored_tokens
    blocks = tuple(
        DifferingBlock(
            tag=tag,
            stored_start=stored_start,
            stored_end=stored_end,
            fresh_start=fresh_start,
            fresh_end=fresh_end,
            stored_rows=tuple(stored_rows[stored_start:stored_end]),
            fresh_rows=tuple(fresh_rows[fresh_start:fresh_end]),
        )
        for tag, stored_start, stored_end, fresh_start, fresh_end in difflib.SequenceMatcher(a=stored_rows, b=fresh_rows, autojunk=False).get_opcodes()
        if tag != _EQUAL_OPCODE
    )
    is_kind_only = [(stored_row.speaker, stored_row.transcript) for stored_row in stored_rows] == [(fresh_row.speaker, fresh_row.transcript) for fresh_row in fresh_rows]
    return RowDifferences(
        blocks=blocks,
        tokens_lost=dict(tokens_lost),
        tokens_gained=dict(tokens_gained),
        word_lost_count=sum(tokens_lost.values()),
        word_gained_count=sum(tokens_gained.values()),
        is_kind_only=is_kind_only,
        is_kind_null_only=is_kind_only and all(stored_row.kind is None or stored_row.kind == fresh_row.kind for stored_row, fresh_row in zip(stored_rows, fresh_rows, strict=True)),
        stored_rows=tuple(stored_rows),
        fresh_rows=tuple(fresh_rows),
    )


def _get_fresh_rows(report: Report, markdown: str, unattributed_range: Optional[UnattributedSpeechRange]) -> Optional[list[ComparedSpeechRow]]:
    start_of_speech_line = get_start_of_speech_line(markdown, report.title, report.subtitle, report.original_title, report.report_type, report.report_version)
    if start_of_speech_line is None:
        return None
    speeches = get_speeches(markdown, start_of_speech_line, report.report_type, report.report_version)
    if unattributed_range is not None:
        speeches = apply_unattributed_speech_range(speeches, unattributed_range)
    return [ComparedSpeechRow(speaker=speech.speaker, transcript=speech.transcript, kind=speech.kind) for speech in speeches]


def _get_fresh_parse(report: Report, unattributed_range: Optional[UnattributedSpeechRange]) -> _FreshParse:
    if report.content is None:
        return _FreshParse(markdown=None, rows=None)
    markdown = get_cleaned_report_markdown(report.content, report.report_version)
    return _FreshParse(markdown=markdown, rows=_get_fresh_rows(report, markdown, unattributed_range))


def _get_status(report: Report, fresh_parse: _FreshParse, stored_rows: list[ComparedSpeechRow], stored_ordinals: list[int]) -> FreshVsStoredStatus:
    if report.content is None:
        return FreshVsStoredStatus.NO_CONTENT
    if fresh_parse.rows is None:
        return FreshVsStoredStatus.NO_START_LINE
    return compare_rows(stored_rows, stored_ordinals, fresh_parse.rows)


def _compare_report(
    report: Report, speech_rows: list[SpeechParseRow], held_reason: Optional[str], unattributed_range: Optional[UnattributedSpeechRange]
) -> FreshVsStoredReport:
    stored_rows = [ComparedSpeechRow(speaker=speech_row.speaker, transcript=speech_row.transcript, kind=speech_row.kind) for speech_row in speech_rows]
    try:
        fresh_parse = _get_fresh_parse(report, unattributed_range)
    except Exception:  # noqa: BLE001 a corpus survey must record every failing report, not stop at the first
        return FreshVsStoredReport(
            id=report.id,
            report_id=report.report_id,
            report_type=report.report_type,
            report_version=report.report_version,
            parliament_number=report.parliament_number,
            title=report.title,
            held_reason=held_reason,
            status=FreshVsStoredStatus.ERROR,
            stored_row_count=len(stored_rows),
            fresh_row_count=None,
            is_markdown_different=None,
            error=traceback.format_exc(limit=_TRACEBACK_LIMIT),
            differences=None,
        )
    status = _get_status(report, fresh_parse, stored_rows, [speech_row.ordinal for speech_row in speech_rows])
    return FreshVsStoredReport(
        id=report.id,
        report_id=report.report_id,
        report_type=report.report_type,
        report_version=report.report_version,
        parliament_number=report.parliament_number,
        title=report.title,
        held_reason=held_reason,
        status=status,
        stored_row_count=len(stored_rows),
        fresh_row_count=0 if fresh_parse.rows is None else len(fresh_parse.rows),
        is_markdown_different=report.markdown_content != fresh_parse.markdown,
        error=None,
        differences=get_row_differences(stored_rows, fresh_parse.rows) if status == FreshVsStoredStatus.CONTENT and fresh_parse.rows is not None else None,
    )


def _compare_report_batch(
    report_ids: list[int], held_report_id_to_reason: dict[int, str], report_id_to_unattributed_range: dict[int, UnattributedSpeechRange]
) -> list[FreshVsStoredReport]:
    with Session(_READ_ONLY_ENGINE) as session:
        report_id_to_speech_rows = defaultdict(list)
        for speech_row in CRUDSpeech(session).get_parse_rows_by_report_ids(report_ids):
            report_id_to_speech_rows[speech_row.report_id].append(speech_row)
        return [
            _compare_report(report, report_id_to_speech_rows[report.id], held_report_id_to_reason.get(report.id), report_id_to_unattributed_range.get(report.id))
            for report in CRUDReport(session).get_by_ids(report_ids)
        ]


def _get_report_ids_to_compare(report_ids: list[int]) -> list[int]:
    if report_ids:
        return report_ids
    with Session(_READ_ONLY_ENGINE) as session:
        return CRUDReport(session).get_ids()


def fresh_vs_stored(output_path: Path, held_path: Path, report_ids: list[int]) -> None:
    held_report_id_to_reason = {held_report.report_id: held_report.reason for held_report in HeldReports.model_validate_json(held_path.read_text()).root}
    report_id_to_unattributed_range = {speech_range.report_id: speech_range for speech_range in get_unattributed_speech_ranges()}
    report_ids_to_compare = _get_report_ids_to_compare(report_ids)
    report_batches = [report_ids_to_compare[start : start + _REPORT_BATCH] for start in range(0, len(report_ids_to_compare), _REPORT_BATCH)]
    logger.info(f"{len(report_ids_to_compare):,} reports in {len(report_batches):,} batches, {_WORKER_COUNT} workers")

    fresh_vs_stored_reports = []
    next_progress = _PROGRESS_EVERY
    compare_report_batch = partial(
        _compare_report_batch, held_report_id_to_reason=held_report_id_to_reason, report_id_to_unattributed_range=report_id_to_unattributed_range
    )
    with Pool(_WORKER_COUNT, maxtasksperchild=_TASKS_PER_WORKER) as pool:
        for batch_reports in pool.imap_unordered(compare_report_batch, report_batches):
            fresh_vs_stored_reports.extend(batch_reports)
            if len(fresh_vs_stored_reports) >= next_progress:
                logger.info(f"Compared {len(fresh_vs_stored_reports):,}/{len(report_ids_to_compare):,} reports")
                next_progress += _PROGRESS_EVERY
    fresh_vs_stored_reports.sort(key=lambda fresh_vs_stored_report: fresh_vs_stored_report.id)
    output_path.write_text(FreshVsStoredReports(fresh_vs_stored_reports).model_dump_json())

    status_counts = Counter(fresh_vs_stored_report.status for fresh_vs_stored_report in fresh_vs_stored_reports)
    held_status_counts = Counter(fresh_vs_stored_report.status for fresh_vs_stored_report in fresh_vs_stored_reports if fresh_vs_stored_report.held_reason is not None)
    kind_only_count = sum(
        fresh_vs_stored_report.differences is not None and fresh_vs_stored_report.differences.is_kind_only for fresh_vs_stored_report in fresh_vs_stored_reports
    )
    logger.info(
        f"Done: {len(fresh_vs_stored_reports):,} reports. "
        + ", ".join(f"{status.value} {status_counts[status]:,}" for status in FreshVsStoredStatus)
        + f". {kind_only_count:,} of the CONTENT reports differ in kind only. Held: "
        + ", ".join(f"{status.value} {held_status_counts[status]:,}" for status in FreshVsStoredStatus)
        + f". Written to {output_path}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare every report's stored speech rows with a fresh parse by the current parser, in read-only transactions")
    parser.add_argument("output", type=Path, help="the JSON file of compared reports to write")
    parser.add_argument("--held", type=Path, required=True, help="a JSON list of {report_id, reason}: reports marked held in the output")
    parser.add_argument("--report-id", type=int, nargs="+", action="extend", default=[], help="only these reports; without it every report")
    arguments = parser.parse_args()
    fresh_vs_stored(arguments.output, arguments.held, arguments.report_id)
