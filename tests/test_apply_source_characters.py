import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_source_characters as apply_source_characters_script
from database.report import Report
from database.sitting import Sitting
from database.speech import Speech
from enums import ReportType, ReportVersion
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from utils.text import TextChange

_SITTING_DATE = datetime(2025, 4, 2)
_BROKEN_TEXT = "the faÃ§ade of the"
_REPAIRED_TEXT = "the façade of the"
_CLEAN_TEXT = "nothing to repair"
_EMPTIED_TEXT = "\ufeff"
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"


def _build_report(markdown_content: str, report_id: str) -> Report:
    return Report(
        volumeNo=14,
        parlNo=14,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title="report",
        title="report",
        reportId=report_id,
        reportType=ReportType.MOTION,
        content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
        markdown_content=markdown_content,
    )


def _seed_repairable_and_clean_rows(scratch_session: Session) -> tuple[Report, Report, Sitting, Speech, Speech, Speech]:
    broken_report = _build_report(_BROKEN_TEXT, "broken")
    clean_report = _build_report(_CLEAN_TEXT, "clean")
    sitting = Sitting(sitting_date="2025-04-02", markdown_content=_BROKEN_TEXT)
    scratch_session.add_all([broken_report, clean_report, sitting])
    scratch_session.flush()
    assert broken_report.id is not None
    broken_speech = Speech(ordinal=1, speaker=_BROKEN_TEXT, transcript=_BROKEN_TEXT, sitting_date=_SITTING_DATE, report_type=broken_report.report_type, report_id=broken_report.id)
    clean_speech = Speech(ordinal=2, speaker="Mr A", transcript=_CLEAN_TEXT, sitting_date=_SITTING_DATE, report_type=broken_report.report_type, report_id=broken_report.id)
    emptied_speech = Speech(ordinal=3, speaker="Mr B", transcript=_EMPTIED_TEXT, sitting_date=_SITTING_DATE, report_type=broken_report.report_type, report_id=broken_report.id)
    scratch_session.add_all([broken_speech, clean_speech, emptied_speech])
    scratch_session.commit()
    return broken_report, clean_report, sitting, broken_speech, clean_speech, emptied_speech


def _get_stored_texts(scratch_session: Session, seeded: tuple[Report, Report, Sitting, Speech, Speech, Speech]) -> list[str | None]:
    broken_report, clean_report, sitting, broken_speech, clean_speech, emptied_speech = seeded
    scratch_session.expire_all()
    return [
        scratch_session.get_one(Report, broken_report.id).markdown_content,
        scratch_session.get_one(Report, clean_report.id).markdown_content,
        scratch_session.get_one(Sitting, sitting.id).markdown_content,
        scratch_session.get_one(Speech, broken_speech.id).transcript,
        scratch_session.get_one(Speech, broken_speech.id).speaker,
        scratch_session.get_one(Speech, clean_speech.id).transcript,
        scratch_session.get_one(Speech, emptied_speech.id).transcript,
    ]


_STORED_BEFORE = [_BROKEN_TEXT, _CLEAN_TEXT, _BROKEN_TEXT, _BROKEN_TEXT, _BROKEN_TEXT, _CLEAN_TEXT, _EMPTIED_TEXT]
_STORED_AFTER = [_REPAIRED_TEXT, _CLEAN_TEXT, _REPAIRED_TEXT, _REPAIRED_TEXT, _REPAIRED_TEXT, _CLEAN_TEXT, _EMPTIED_TEXT]


def test_dry_run_writes_the_plan_and_changes_no_row(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_source_characters_script, "engine", scratch_engine)
    seeded = _seed_repairable_and_clean_rows(scratch_session)
    broken_report, _, sitting, broken_speech, _, emptied_speech = seeded
    plan_path = tmp_path / "plan.json"

    apply_source_characters_script.apply_source_characters(is_commit=False, plan_path=plan_path)

    plan = json.loads(plan_path.read_text())
    assert plan == {
        "speech_transcripts": [{"id": broken_speech.id, "before": _BROKEN_TEXT, "after": _REPAIRED_TEXT}],
        "speech_labels": [{"id": broken_speech.id, "before": _BROKEN_TEXT, "after": _REPAIRED_TEXT}],
        "report_markdowns": [{"id": broken_report.id, "before": _BROKEN_TEXT, "after": _REPAIRED_TEXT}],
        "sitting_markdowns": [{"id": sitting.id, "before": _BROKEN_TEXT, "after": _REPAIRED_TEXT}],
        "emptied_speech_ids": [emptied_speech.id],
    }
    assert _get_stored_texts(scratch_session, seeded) == _STORED_BEFORE


def test_commit_refuses_after_a_planned_row_changes(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(apply_source_characters_script, "engine", scratch_engine)
    seeded = _seed_repairable_and_clean_rows(scratch_session)
    broken_report, _, sitting, broken_speech, _, emptied_speech = seeded
    stale_plan = apply_source_characters_script.SourceCharacterPlan(
        [TextChange(broken_speech.id, _BROKEN_TEXT, _REPAIRED_TEXT)],
        [TextChange(broken_speech.id, _BROKEN_TEXT, _REPAIRED_TEXT)],
        [TextChange(broken_report.id, _BROKEN_TEXT, _REPAIRED_TEXT)],
        [TextChange(sitting.id, _BROKEN_TEXT, _REPAIRED_TEXT)],
        [emptied_speech.id],
    )
    scratch_session.get_one(Report, broken_report.id).markdown_content = "changed after the plan"
    scratch_session.commit()
    monkeypatch.setattr(apply_source_characters_script, "_get_source_character_plan", lambda session: stale_plan)

    with pytest.raises(HansardWriteCheckError, match="Rows changed since the plan was made"):
        apply_source_characters_script.apply_source_characters(is_commit=True, plan_path=None)

    stored_texts = _get_stored_texts(scratch_session, seeded)
    assert stored_texts[0] == "changed after the plan"
    assert stored_texts[1:] == _STORED_BEFORE[1:]


def test_commit_on_an_unchanged_state_writes_exactly_the_plan(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(apply_source_characters_script, "engine", scratch_engine)
    seeded = _seed_repairable_and_clean_rows(scratch_session)

    apply_source_characters_script.apply_source_characters(is_commit=True, plan_path=None)

    assert _get_stored_texts(scratch_session, seeded) == _STORED_AFTER


def test_commit_refuses_the_protected_local_port_and_writes_nothing(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(apply_source_characters_script, "engine", scratch_engine)
    seeded = _seed_repairable_and_clean_rows(scratch_session)
    monkeypatch.setattr(apply_source_characters_script, "settings", SimpleNamespace(database_url=_PROTECTED_DATABASE_URL))

    with pytest.raises(HansardWriteTargetError, match="5432"):
        apply_source_characters_script.apply_source_characters(is_commit=True, plan_path=None)

    assert _get_stored_texts(scratch_session, seeded) == _STORED_BEFORE
