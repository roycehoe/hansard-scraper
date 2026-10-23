from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from sqlmodel import Session

from crud.report import CRUDReport
from crud.speech import CRUDSpeech, SpeechColumnRow
from database.report import Report
from enums import ColumnNote, MissingColumnReason
from exceptions import HansardWriteCheckError
from utils.column_numbers import (
    ReportColumnRange,
    SpeechColumnNote,
    SpeechText,
    build_column_text,
    get_column_markers,
    get_head_column_range,
    get_report_column_range,
    get_speech_columns,
)

_REPORT_BATCH = 200
_WRITE_BATCH = 10_000


@dataclass
class ColumnNumberCounts:
    reports: int = 0
    reports_with_markers: int = 0
    reports_with_range: int = 0
    rows: int = 0
    rows_with_column: int = 0
    missing_column_reason_counts: Counter[MissingColumnReason] = field(default_factory=Counter)
    column_note_counts: Counter[ColumnNote] = field(default_factory=Counter)


@dataclass
class ColumnNumberPlan:
    report_ids: list[int]
    parliament_to_counts: defaultdict[int, ColumnNumberCounts] = field(default_factory=lambda: defaultdict(ColumnNumberCounts))
    report_column_ranges: list[ReportColumnRange] = field(default_factory=list)
    speech_id_to_column_start: dict[int, Optional[int]] = field(default_factory=dict)
    speech_column_notes: list[SpeechColumnNote] = field(default_factory=list)


def _add_report(plan: ColumnNumberPlan, report: Report, speech_column_rows: list[SpeechColumnRow]) -> None:
    counts = plan.parliament_to_counts[report.parliament_number]
    column_text = build_column_text(report.content or "")
    column_markers = get_column_markers(column_text)
    head_column_range = get_head_column_range(report.content or "")
    column_range = get_report_column_range(column_markers, head_column_range)
    report_column_range = ReportColumnRange(
        report.id,
        None if column_range is None else column_range.column_start,
        None if column_range is None else column_range.column_end,
    )
    counts.reports += 1
    counts.reports_with_markers += len(column_markers) > 0
    counts.reports_with_range += column_range is not None
    if report_column_range != ReportColumnRange(report.id, report.column_start, report.column_end):
        plan.report_column_ranges.append(report_column_range)
    speech_texts = [SpeechText(speech_column_row.speaker, speech_column_row.transcript) for speech_column_row in speech_column_rows]
    for speech_column_row, speech_column in zip(speech_column_rows, get_speech_columns(column_text, column_markers, head_column_range, speech_texts), strict=True):
        counts.rows += 1
        if speech_column.column_start is not None:
            counts.rows_with_column += 1
        if speech_column.missing_column_reason is not None:
            counts.missing_column_reason_counts[speech_column.missing_column_reason] += 1
        if speech_column.column_note is not None:
            counts.column_note_counts[speech_column.column_note] += 1
        if speech_column.column_start != speech_column_row.column_start:
            plan.speech_id_to_column_start[speech_column_row.id] = speech_column.column_start
        speech_column_note = SpeechColumnNote(speech_column_row.id, speech_column.column_note, speech_column.column_suggested)
        if speech_column_note != SpeechColumnNote(speech_column_row.id, speech_column_row.column_note, speech_column_row.column_suggested):
            plan.speech_column_notes.append(speech_column_note)


def get_column_number_plan(session: Session, report_ids: list[int]) -> ColumnNumberPlan:
    plan = ColumnNumberPlan(sorted(report_ids))
    for start in range(0, len(plan.report_ids), _REPORT_BATCH):
        batch_report_ids = plan.report_ids[start : start + _REPORT_BATCH]
        report_id_to_speech_column_rows = defaultdict(list)
        for speech_column_row in CRUDSpeech(session).get_column_rows_by_report_ids(batch_report_ids):
            report_id_to_speech_column_rows[speech_column_row.report_id].append(speech_column_row)
        for report in CRUDReport(session).get_by_ids(batch_report_ids):
            _add_report(plan, report, report_id_to_speech_column_rows[report.id])
        session.expunge_all()
    return plan


def _get_stored_counts(session: Session, report_ids: list[int]) -> defaultdict[int, ColumnNumberCounts]:
    parliament_to_counts = defaultdict(ColumnNumberCounts)
    for start in range(0, len(report_ids), _REPORT_BATCH):
        batch_report_ids = report_ids[start : start + _REPORT_BATCH]
        report_id_to_parliament_number = {}
        for report_column_row in CRUDReport(session).get_column_rows_by_ids(batch_report_ids):
            report_id_to_parliament_number[report_column_row.id] = report_column_row.parliament_number
            parliament_to_counts[report_column_row.parliament_number].reports_with_range += report_column_row.column_start is not None
        for speech_column_row in CRUDSpeech(session).get_column_rows_by_report_ids(batch_report_ids):
            counts = parliament_to_counts[report_id_to_parliament_number[speech_column_row.report_id]]
            counts.rows_with_column += speech_column_row.column_start is not None
            if speech_column_row.column_note is not None:
                counts.column_note_counts[speech_column_row.column_note] += 1
    return parliament_to_counts


def _validate_can_commit_column_numbers(session: Session, plan: ColumnNumberPlan) -> None:
    stored_parliament_to_counts = _get_stored_counts(session, plan.report_ids)
    for parliament_number, counts in plan.parliament_to_counts.items():
        stored_counts = stored_parliament_to_counts[parliament_number]
        if stored_counts.reports_with_range != counts.reports_with_range:
            raise HansardWriteCheckError(f"Parliament {parliament_number}: {stored_counts.reports_with_range} reports hold a column range, the plan has {counts.reports_with_range}")
        if stored_counts.rows_with_column != counts.rows_with_column:
            raise HansardWriteCheckError(f"Parliament {parliament_number}: {stored_counts.rows_with_column} speech rows hold a start column, the plan has {counts.rows_with_column}")
        if stored_counts.column_note_counts != counts.column_note_counts:
            raise HansardWriteCheckError(f"Parliament {parliament_number}: stored column notes {dict(stored_counts.column_note_counts)}, the plan has {dict(counts.column_note_counts)}")


def write_column_number_plan(session: Session, plan: ColumnNumberPlan) -> None:
    report_count = CRUDReport(session).set_column_ranges_bulk(plan.report_column_ranges)
    if report_count != len(plan.report_column_ranges):
        raise HansardWriteCheckError(f"Updated {report_count} report column ranges, planned {len(plan.report_column_ranges)}")
    speech_ids = list(plan.speech_id_to_column_start)
    column_start_count = 0
    for start in range(0, len(speech_ids), _WRITE_BATCH):
        column_start_count += CRUDSpeech(session).set_column_starts_bulk(
            {speech_id: plan.speech_id_to_column_start[speech_id] for speech_id in speech_ids[start : start + _WRITE_BATCH]}
        )
    if column_start_count != len(speech_ids):
        raise HansardWriteCheckError(f"Updated {column_start_count} speech start columns, planned {len(speech_ids)}")
    column_note_count = 0
    for start in range(0, len(plan.speech_column_notes), _WRITE_BATCH):
        column_note_count += CRUDSpeech(session).set_column_notes_bulk(plan.speech_column_notes[start : start + _WRITE_BATCH])
    if column_note_count != len(plan.speech_column_notes):
        raise HansardWriteCheckError(f"Updated {column_note_count} speech column notes, planned {len(plan.speech_column_notes)}")
    _validate_can_commit_column_numbers(session, plan)
