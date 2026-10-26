from datetime import datetime
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.apply_column_numbers as apply_column_numbers_script
from crud.speech import CRUDSpeech
from database.report import Report
from database.speech import Speech
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from scripts.apply_column_numbers import apply_column_numbers
from services.speech import build_report_speeches
from utils.markdown_parser import get_cleaned_report_markdown

_SITTING_DATE = datetime(2013, 1, 14)
_REPORT_HTML = "<p>Column: 12</p><p><strong>Mr A</strong>: First.</p><p>Column: 13</p><p><strong>Mr B</strong>: Second.</p>"
_PLAN_LOG = "Plan: 1 report column ranges, 2 speech start columns and 0 speech column notes differ from the stored rows"
_EMPTY_PLAN_LOG = "Plan: 0 report column ranges, 0 speech start columns and 0 speech column notes differ from the stored rows"
_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _seed_report(session: Session, report_id: str) -> Report:
    report = Report(
        volumeNo=1,
        parlNo=12,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title="Sample Question",
        title="Sample Question",
        reportId=report_id,
        reportType="oral-answer",
        content=_REPORT_HTML,
        markdown_content=get_cleaned_report_markdown(_REPORT_HTML, "sprs3"),
        htmlFileName=None,
        reportVersion="sprs3",
    )
    session.add(report)
    session.flush()
    assert report.id is not None
    parsed_speeches = build_report_speeches(report, {}).speeches
    session.add_all(
        Speech(ordinal=ordinal, speaker=parsed_speech.speaker, transcript=parsed_speech.transcript, sitting_date=_SITTING_DATE, report_id=report.id)
        for ordinal, parsed_speech in enumerate(parsed_speeches, start=1)
    )
    session.commit()
    return report


def _get_report_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return [(report.report_id, report.column_start, report.column_end, report.content, report.markdown_content) for report in session.exec(select(Report).order_by(Report.id)).all()]


def _get_speech_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (speech.report_id, speech.ordinal, speech.speaker, speech.transcript, speech.column_start, speech.column_note, speech.column_suggested)
        for speech in session.exec(select(Speech).order_by(Speech.id)).all()
    ]


@pytest.fixture
def log_recorder(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_column_numbers_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_column_numbers_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(scratch_session: Session, log_recorder: _LogRecorder) -> None:
    _seed_report(scratch_session, "report-a")
    report_rows_before = _get_report_rows(scratch_session)
    speech_rows_before = _get_speech_rows(scratch_session)

    apply_column_numbers([], is_commit=False)

    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_report_rows(scratch_session) == report_rows_before
    assert _get_speech_rows(scratch_session) == speech_rows_before


def test_commit_with_report_ids_leaves_other_reports_untouched(scratch_session: Session, log_recorder: _LogRecorder) -> None:
    first_report = _seed_report(scratch_session, "report-a")
    second_report = _seed_report(scratch_session, "report-b")
    _, second_report_row_before = _get_report_rows(scratch_session)
    second_report_speech_rows_before = [row for row in _get_speech_rows(scratch_session) if row[0] == second_report.id]

    apply_column_numbers([first_report.id], is_commit=True)

    (_, first_column_start, first_column_end, *_), second_report_row = _get_report_rows(scratch_session)
    assert (first_column_start, first_column_end) == (12, 13)
    assert second_report_row == second_report_row_before
    speech_rows = _get_speech_rows(scratch_session)
    assert [column_start for report_id, _, _, _, column_start, *_ in speech_rows if report_id == first_report.id] == [12, 13]
    assert [row for row in speech_rows if row[0] == second_report.id] == second_report_speech_rows_before


def test_commit_on_unchanged_state_writes_exactly_the_plan(scratch_session: Session, log_recorder: _LogRecorder) -> None:
    _seed_report(scratch_session, "report-a")
    report_rows_before = _get_report_rows(scratch_session)
    speech_rows_before = _get_speech_rows(scratch_session)

    apply_column_numbers([], is_commit=True)

    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Committed"
    expected_report_rows = [(report_id, 12, 13, content, markdown_content) for report_id, _, _, content, markdown_content in report_rows_before]
    expected_speech_rows = [
        (report_id, ordinal, speaker, transcript, column_start, column_note, column_suggested)
        for (report_id, ordinal, speaker, transcript, _, column_note, column_suggested), column_start in zip(speech_rows_before, [12, 13], strict=True)
    ]
    assert _get_report_rows(scratch_session) == expected_report_rows
    assert _get_speech_rows(scratch_session) == expected_speech_rows

    apply_column_numbers([], is_commit=True)

    assert _EMPTY_PLAN_LOG in log_recorder.messages
    assert _get_report_rows(scratch_session) == expected_report_rows
    assert _get_speech_rows(scratch_session) == expected_speech_rows


def test_commit_refuses_the_protected_port_before_any_row_is_written(scratch_session: Session, log_recorder: _LogRecorder, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_report(scratch_session, "report-a")
    report_rows_before = _get_report_rows(scratch_session)
    speech_rows_before = _get_speech_rows(scratch_session)
    monkeypatch.setattr(apply_column_numbers_script, "settings", SimpleNamespace(database_url=_PROTECTED_DATABASE_URL))

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_column_numbers([], is_commit=True)

    assert _get_report_rows(scratch_session) == report_rows_before
    assert _get_speech_rows(scratch_session) == speech_rows_before


def test_commit_refuses_a_short_update_count_and_keeps_the_rows(scratch_session: Session, log_recorder: _LogRecorder, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_report(scratch_session, "report-a")
    report_rows_before = _get_report_rows(scratch_session)
    speech_rows_before = _get_speech_rows(scratch_session)
    real_set_column_starts_bulk = CRUDSpeech.set_column_starts_bulk

    def set_column_starts_bulk_one_short(self: CRUDSpeech, speech_id_to_column_start: dict[int, Optional[int]]) -> int:
        return real_set_column_starts_bulk(self, speech_id_to_column_start) - 1

    monkeypatch.setattr(CRUDSpeech, "set_column_starts_bulk", set_column_starts_bulk_one_short)

    with pytest.raises(HansardWriteCheckError, match="Updated 1 speech start columns, planned 2"):
        apply_column_numbers([], is_commit=True)

    assert _get_report_rows(scratch_session) == report_rows_before
    assert _get_speech_rows(scratch_session) == speech_rows_before
