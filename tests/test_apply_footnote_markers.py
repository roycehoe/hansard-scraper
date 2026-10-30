from datetime import datetime
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.apply_footnote_markers as apply_footnote_markers_script
from crud.speech import CRUDSpeech
from database.report import Report
from database.speech import Speech
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from scripts.apply_footnote_markers import apply_footnote_markers
from services.speech import build_report_speeches
from utils.markdown_parser import get_cleaned_report_markdown

_SITTING_DATE = datetime(2013, 1, 14)
_REPORT_HTML = (
    "<p>Column: 12</p><p><strong>Mr A</strong>: The plot is 5 km<sup>2</sup> wide.</p>"
    "<p><strong>Mr B</strong>: Plan A<sup>1</sup> is Tan's<sup>2</sup> idea.</p><p><strong>Mr A</strong>: Noted.</p>"
)
_PARSED_PHRASE = "Plan A[1] is Tan's[2] idea."
_STORED_PHRASE = "Plan A1 is Tan's2 idea."
_PLAN_LOG_START = "Plan: 1 report markdowns and 1 transcripts in 1 reports gain a footnote marker"
_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _seed_report(session: Session, speech_count: Optional[int] = None) -> Report:
    report = Report(
        volumeNo=1,
        parlNo=12,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title="Sample Question",
        title="Sample Question",
        reportId="report-a",
        reportType="oral-answer",
        content=_REPORT_HTML,
        markdown_content=get_cleaned_report_markdown(_REPORT_HTML, "sprs3").replace(_PARSED_PHRASE, _STORED_PHRASE),
        htmlFileName=None,
        reportVersion="sprs3",
    )
    session.add(report)
    session.flush()
    assert report.id is not None
    parsed_speeches = build_report_speeches(report, {}).speeches[:speech_count]
    session.add_all(
        Speech(
            ordinal=ordinal,
            speaker=parsed_speech.speaker,
            transcript=parsed_speech.transcript.replace(_PARSED_PHRASE, _STORED_PHRASE),
            sitting_date=_SITTING_DATE,
            report_type=report.report_type,
            report_id=report.id,
        )
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
        (speech.ordinal, speech.speaker, speech.transcript, speech.column_start, speech.column_note, speech.column_suggested)
        for speech in session.exec(select(Speech).order_by(Speech.id)).all()
    ]


@pytest.fixture
def log_recorder(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_footnote_markers_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_footnote_markers_script, "logger", recorder)
    monkeypatch.setattr(apply_footnote_markers_script, "get_unattributed_speech_ranges", list)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(scratch_session: Session, log_recorder: _LogRecorder) -> None:
    _seed_report(scratch_session)
    report_rows_before = _get_report_rows(scratch_session)
    speech_rows_before = _get_speech_rows(scratch_session)

    apply_footnote_markers(is_commit=False)

    assert log_recorder.messages[0].startswith(_PLAN_LOG_START)
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_report_rows(scratch_session) == report_rows_before
    assert _get_speech_rows(scratch_session) == speech_rows_before


def test_commit_on_unchanged_state_writes_exactly_the_plan(scratch_session: Session, log_recorder: _LogRecorder) -> None:
    _seed_report(scratch_session)
    report_rows_before = _get_report_rows(scratch_session)
    speech_rows_before = _get_speech_rows(scratch_session)

    apply_footnote_markers(is_commit=True)

    assert log_recorder.messages[0].startswith(_PLAN_LOG_START)
    expected_report_rows = [
        (report_id, 12, 12, content, markdown_content.replace(_STORED_PHRASE, _PARSED_PHRASE)) for report_id, _, _, content, markdown_content in report_rows_before
    ]
    expected_speech_rows = [
        (ordinal, speaker, transcript.replace(_STORED_PHRASE, _PARSED_PHRASE), 12, column_note, column_suggested)
        for ordinal, speaker, transcript, _, column_note, column_suggested in speech_rows_before
    ]
    assert _get_report_rows(scratch_session) == expected_report_rows
    assert _get_speech_rows(scratch_session) == expected_speech_rows

    first_run_message_count = len(log_recorder.messages)

    apply_footnote_markers(is_commit=True)

    assert log_recorder.messages[first_run_message_count].startswith("Plan: 0 report markdowns and 0 transcripts in 0 reports")
    assert _get_report_rows(scratch_session) == expected_report_rows
    assert _get_speech_rows(scratch_session) == expected_speech_rows


def test_commit_refuses_and_writes_nothing_when_the_transcripts_changed_since_the_plan(
    scratch_session: Session, log_recorder: _LogRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_report(scratch_session)
    report_rows_before = _get_report_rows(scratch_session)
    speech_rows_before = _get_speech_rows(scratch_session)
    monkeypatch.setattr(CRUDSpeech, "set_transcripts_bulk_by_transcript", lambda self, transcript_changes: 0)

    with pytest.raises(HansardWriteCheckError, match="Rows changed since the plan was made: planned 1, written 0"):
        apply_footnote_markers(is_commit=True)

    assert _get_report_rows(scratch_session) == report_rows_before
    assert _get_speech_rows(scratch_session) == speech_rows_before


def test_report_whose_parse_has_another_row_count_keeps_its_speech_rows(scratch_session: Session, log_recorder: _LogRecorder) -> None:
    report = _seed_report(scratch_session, speech_count=2)
    speech_rows_before = _get_speech_rows(scratch_session)

    apply_footnote_markers(is_commit=True)

    assert f"1 reports whose parse has another row count ({report.id})" in log_recorder.messages[0]
    assert _get_speech_rows(scratch_session) == speech_rows_before


def test_commit_refuses_the_protected_port_before_any_row_is_written(scratch_session: Session, log_recorder: _LogRecorder, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_report(scratch_session)
    report_rows_before = _get_report_rows(scratch_session)
    speech_rows_before = _get_speech_rows(scratch_session)
    monkeypatch.setattr(apply_footnote_markers_script, "settings", SimpleNamespace(database_url=_PROTECTED_DATABASE_URL))

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_footnote_markers(is_commit=True)

    assert _get_report_rows(scratch_session) == report_rows_before
    assert _get_speech_rows(scratch_session) == speech_rows_before
