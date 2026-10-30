import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.remove_excluded_reports as remove_excluded_reports_script
from database.report import Report
from database.speech import Speech
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.excluded_report_id import ExcludedReportId

_SITTING_DATE = datetime(2007, 10, 22)
_KEPT_REPORT_ID = "kept-report"
_EXCLUDED_REPORT_ID = "excluded-report"
_TEXT = "Same text."
_SEEDED_SPEECH_COUNT = 2


def _add_report(session: Session, report_id: str, content: str) -> Report:
    report = Report(
        volume_number=83, parliament_number=11, sitting_date=_SITTING_DATE, speech_number=1, original_title="Bill", title="Bill",
        report_id=report_id, report_type="bill", content=content, report_version="sprs2",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _add_speech(session: Session, report: Report) -> None:
    assert report.id is not None
    session.add(Speech(ordinal=1, speaker="Mr A", transcript="Hello.", sitting_date=_SITTING_DATE, report_type=report.report_type, report_id=report.id))
    session.commit()


def _seed_duplicate(session: Session, excluded_content: str = _TEXT) -> None:
    for report_id, content in ((_KEPT_REPORT_ID, _TEXT), (_EXCLUDED_REPORT_ID, excluded_content)):
        _add_speech(session, _add_report(session, report_id, content))


def _use_scratch(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(remove_excluded_reports_script, "engine", scratch_engine)
    excluded_report_ids = [ExcludedReportId(report_id=_EXCLUDED_REPORT_ID, kept_report_id=_KEPT_REPORT_ID, reason="duplicate")]
    monkeypatch.setattr(remove_excluded_reports_script, "get_excluded_report_ids", lambda: excluded_report_ids)


def _get_report_ids(session: Session) -> list[str]:
    session.expire_all()
    return sorted(session.exec(select(Report.report_id)).all())


def _get_speech_count(session: Session) -> int:
    session.expire_all()
    return len(session.exec(select(Speech.id)).all())


def test_dry_run_writes_the_plan_and_no_rows(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)
    plan_path = tmp_path / "plan.json"

    remove_excluded_reports_script.remove_excluded_reports(False, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [(removal["report_id"], removal["kept_report_id"], removal["speech_count"]) for removal in plan] == [(_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID, 1)]
    assert _get_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == _SEEDED_SPEECH_COUNT


def test_commit_refuses_when_the_duplicate_text_differs(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session, excluded_content="Different text.")

    with pytest.raises(HansardWriteCheckError, match="text differs"):
        remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == _SEEDED_SPEECH_COUNT


def test_commit_deletes_exactly_the_planned_report_and_speeches(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _seed_duplicate(scratch_session)

    remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == 1
    remove_excluded_reports_script.remove_excluded_reports(True, None)
    assert _get_report_ids(scratch_session) == [_KEPT_REPORT_ID]
    assert _get_speech_count(scratch_session) == 1


def test_commit_refuses_the_protected_local_port(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    monkeypatch.setattr(remove_excluded_reports_script, "settings", SimpleNamespace(database_url="postgresql://u:p@localhost:5432/x"))
    _seed_duplicate(scratch_session)

    with pytest.raises(HansardWriteTargetError):
        remove_excluded_reports_script.remove_excluded_reports(True, None)

    assert _get_report_ids(scratch_session) == [_EXCLUDED_REPORT_ID, _KEPT_REPORT_ID]
