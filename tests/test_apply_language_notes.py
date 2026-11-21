import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.apply_language_notes as apply_language_notes_script
from crud.speech import CRUDSpeech
from database.report import Report
from database.speech import Speech
from enums import ReportVersion, SpeechKind
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from scripts.apply_language_notes import apply_language_notes
from utils.markdown_parser import get_cleaned_report_markdown

_FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "language_note_after_a_bold_label_is_kept_beside_the_label.json"
)
_SITTING_DATE = datetime(1960, 4, 6)
_EDITED_TRANSCRIPT = "Mr Speaker, as one of the women of Singapore."
_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _seed_report(session: Session, is_last_row_edited: bool) -> dict:
    fixture = json.loads(_FIXTURE_PATH.read_text())
    report = Report(
        volumeNo=12,
        parlNo=0,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title=fixture["original_title"],
        title=fixture["title"],
        reportId="fixture",
        reportType=fixture["report_type"],
        content=fixture["html"],
        markdown_content=get_cleaned_report_markdown(
            fixture["html"], ReportVersion.SPRS2
        ),
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS2,
    )
    session.add(report)
    session.flush()
    row_count = len(fixture["expected_rows"])
    session.add_all(
        Speech(
            ordinal=ordinal,
            speaker=speaker,
            transcript=_EDITED_TRANSCRIPT
            if is_last_row_edited and ordinal == row_count
            else transcript,
            kind=SpeechKind(kind),
            sitting_date=_SITTING_DATE,
            report_type=report.report_type,
            report_id=report.id,
        )
        for ordinal, (speaker, transcript, kind) in enumerate(
            fixture["expected_rows"], start=1
        )
    )
    session.commit()
    return fixture


def _get_speech_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (
            speech.id,
            speech.ordinal,
            speech.speaker,
            speech.transcript,
            speech.kind,
            speech.speaker_id,
            speech.language_note,
        )
        for speech in session.exec(select(Speech).order_by(Speech.id)).all()
    ]


def _get_report_id(session: Session) -> int:
    report_id = session.exec(select(Report.id)).one()
    assert report_id is not None
    return report_id


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_language_notes_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_language_notes_script, "logger", recorder)
    monkeypatch.setattr(
        apply_language_notes_script, "get_unlabelled_speech_ranges", list
    )
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_report(scratch_session, is_last_row_edited=False)
    speech_rows_before = _get_speech_rows(scratch_session)

    apply_language_notes([], is_commit=False)

    assert log_recorder.messages[-2].startswith(
        "Plan: 2 rows take a language note and 0 lose one, in 1 reports."
        " Rows and reports by note: 'In Mandarin' 2 in 1."
    )
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_speech_rows(scratch_session) == speech_rows_before


def test_commit_sets_only_the_language_note_and_a_second_run_plans_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    fixture = _seed_report(scratch_session, is_last_row_edited=False)
    speech_rows_before = _get_speech_rows(scratch_session)

    apply_language_notes([], is_commit=True)

    expected_speech_rows = [
        (*speech_row[:-1], language_note)
        for speech_row, language_note in zip(
            speech_rows_before, fixture["expected_language_notes"], strict=True
        )
    ]
    assert _get_speech_rows(scratch_session) == expected_speech_rows
    assert log_recorder.messages[-1] == "Committed: 2 language notes"

    apply_language_notes([], is_commit=False)

    assert log_recorder.messages[-2].startswith(
        "Plan: 0 rows take a language note and 0 lose one, in 0 reports."
    )
    assert _get_speech_rows(scratch_session) == expected_speech_rows


def test_a_note_whose_row_differs_from_the_parse_is_counted_and_not_written(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    fixture = _seed_report(scratch_session, is_last_row_edited=True)
    row_count = len(fixture["expected_rows"])

    apply_language_notes([], is_commit=True)

    assert "1 paired with a stored row, 1 not paired" in log_recorder.messages[-4]
    assert (
        log_recorder.messages[-3]
        == f"Not paired: report {_get_report_id(scratch_session)} ordinal {row_count} 'In Mandarin'"
    )
    assert [speech_row[-1] for speech_row in _get_speech_rows(scratch_session)] == [
        *fixture["expected_language_notes"][:-1],
        None,
    ]


def test_commit_refuses_and_writes_nothing_when_a_row_changed_since_the_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_report(scratch_session, is_last_row_edited=False)
    speech_rows_before = _get_speech_rows(scratch_session)
    monkeypatch.setattr(
        CRUDSpeech,
        "set_language_notes_bulk_by_ordinal_and_speaker_and_transcript",
        lambda self, language_note_changes: 0,
    )

    with pytest.raises(
        HansardWriteCheckError,
        match="Rows changed since the plan was made: planned 2, written 0",
    ):
        apply_language_notes([], is_commit=True)

    assert _get_speech_rows(scratch_session) == speech_rows_before


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_report(scratch_session, is_last_row_edited=False)
    speech_rows_before = _get_speech_rows(scratch_session)
    monkeypatch.setattr(
        apply_language_notes_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_language_notes([], is_commit=True)

    assert _get_speech_rows(scratch_session) == speech_rows_before
