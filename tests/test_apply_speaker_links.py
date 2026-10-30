import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_speaker_links as apply_speaker_links_script
from database.report import Report
from database.speaker import Speaker
from database.speech import Speech
from enums import ReportType, ReportVersion
from exceptions import HansardWriteCheckError, HansardWriteTargetError

_PARLIAMENT_NUMBER = 14
_SITTING_DATE = datetime(2025, 4, 2)
_SPEAKER_NAME = "Pritam Singh"
_OTHER_SPEAKER_NAME = "Louis Chua"
_SPEAKER_LABEL = "Mr Pritam Singh"
_UNKNOWN_LABEL = "Mr Nobody Known"
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"


def _build_speaker(name: str) -> Speaker:
    return Speaker(name=name, party="WP", is_legislative_assembly=False, parliament_number=_PARLIAMENT_NUMBER)


def _build_report() -> Report:
    return Report(
        volumeNo=_PARLIAMENT_NUMBER,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title="report",
        title="report",
        reportId="report",
        reportType=ReportType.MOTION,
        content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _build_speech(report: Report, ordinal: int, speaker_label: str) -> Speech:
    assert report.id is not None
    return Speech(ordinal=ordinal, speaker=speaker_label, transcript="Text", sitting_date=_SITTING_DATE, report_type=report.report_type, report_id=report.id)


def _seed_speakers_and_speeches(scratch_session: Session) -> tuple[Speaker, Speaker, Speech, Speech]:
    speaker = _build_speaker(_SPEAKER_NAME)
    other_speaker = _build_speaker(_OTHER_SPEAKER_NAME)
    report = _build_report()
    scratch_session.add_all([speaker, other_speaker, report])
    scratch_session.flush()
    linkable_speech = _build_speech(report, 1, _SPEAKER_LABEL)
    unlinkable_speech = _build_speech(report, 2, _UNKNOWN_LABEL)
    scratch_session.add_all([linkable_speech, unlinkable_speech])
    scratch_session.commit()
    return speaker, other_speaker, linkable_speech, unlinkable_speech


def _get_stored_speaker_id(scratch_session: Session, speech: Speech) -> int | None:
    scratch_session.expire_all()
    return scratch_session.get_one(Speech, speech.id).speaker_id


def test_dry_run_writes_the_plan_and_changes_no_row(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_speaker_links_script, "engine", scratch_engine)
    speaker, _, linkable_speech, unlinkable_speech = _seed_speakers_and_speeches(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_speaker_links_script.apply_speaker_links(plan_path, is_commit=False)

    plan = json.loads(plan_path.read_text())
    assert plan == {"speech_id_to_speaker_id": {str(linkable_speech.id): speaker.id}, "attendance_id_to_speaker_id": {}}
    assert _get_stored_speaker_id(scratch_session, linkable_speech) is None
    assert _get_stored_speaker_id(scratch_session, unlinkable_speech) is None


def test_commit_refuses_after_a_planned_row_changes(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_speaker_links_script, "engine", scratch_engine)
    _, other_speaker, linkable_speech, _ = _seed_speakers_and_speeches(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_speaker_links_script.apply_speaker_links(plan_path, is_commit=False)
    scratch_session.get_one(Speech, linkable_speech.id).speaker_id = other_speaker.id
    scratch_session.commit()

    with pytest.raises(HansardWriteCheckError, match="holds speaker"):
        apply_speaker_links_script.apply_speaker_links(plan_path, is_commit=True)

    assert _get_stored_speaker_id(scratch_session, linkable_speech) == other_speaker.id


def test_commit_on_an_unchanged_state_writes_exactly_the_plan(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_speaker_links_script, "engine", scratch_engine)
    speaker, _, linkable_speech, unlinkable_speech = _seed_speakers_and_speeches(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_speaker_links_script.apply_speaker_links(plan_path, is_commit=False)

    apply_speaker_links_script.apply_speaker_links(plan_path, is_commit=True)

    assert _get_stored_speaker_id(scratch_session, linkable_speech) == speaker.id
    assert _get_stored_speaker_id(scratch_session, unlinkable_speech) is None


def test_commit_refuses_the_protected_local_port_and_writes_nothing(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_speaker_links_script, "engine", scratch_engine)
    _, _, linkable_speech, _ = _seed_speakers_and_speeches(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_speaker_links_script.apply_speaker_links(plan_path, is_commit=False)
    monkeypatch.setattr(apply_speaker_links_script, "settings", SimpleNamespace(database_url=_PROTECTED_DATABASE_URL))

    with pytest.raises(HansardWriteTargetError, match="5432"):
        apply_speaker_links_script.apply_speaker_links(plan_path, is_commit=True)

    assert _get_stored_speaker_id(scratch_session, linkable_speech) is None
