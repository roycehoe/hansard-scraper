import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_report_titles as apply_report_titles_script
from database.report import Report
from enums import ReportType, ReportVersion
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from scripts.apply_report_titles import TitleChange

_SITTING_DATE = datetime(2025, 4, 2)
_RAW_TITLE = "Committee of Supply – Head S (Ministry of Manpower) "
_STALE_TITLE = "Committee of Supply – Head S (Ministry of Manpower)"
_BUILT_TITLE = "Committee of Supply – Head S"
_BUILT_SUBTITLE = "(Ministry of Manpower)"
_CURRENT_TITLE = "BUDGET"
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"


def _build_report(original_title: str, title: str, report_id: str) -> Report:
    return Report(
        volumeNo=14,
        parlNo=14,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title=original_title,
        title=title,
        reportId=report_id,
        reportType=ReportType.MOTION,
        content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _seed_reports(scratch_session: Session) -> tuple[Report, Report]:
    stale_report = _build_report(_RAW_TITLE, _STALE_TITLE, "stale")
    current_report = _build_report(_CURRENT_TITLE, _CURRENT_TITLE, "current")
    scratch_session.add_all([stale_report, current_report])
    scratch_session.commit()
    return stale_report, current_report


def _get_stored_titles(scratch_session: Session, seeded: tuple[Report, Report]) -> list[tuple[str, str | None]]:
    scratch_session.expire_all()
    return [(report.title, report.subtitle) for report in (scratch_session.get_one(Report, seeded_report.id) for seeded_report in seeded)]


_BEFORE = [(_STALE_TITLE, None), (_CURRENT_TITLE, None)]
_AFTER = [(_BUILT_TITLE, _BUILT_SUBTITLE), (_CURRENT_TITLE, None)]


def test_dry_run_writes_the_plan_and_changes_no_row(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_report_titles_script, "engine", scratch_engine)
    seeded = _seed_reports(scratch_session)
    stale_report, _ = seeded
    plan_path = tmp_path / "plan.json"

    apply_report_titles_script.apply_report_titles(is_commit=False, plan_path=plan_path)

    plan = json.loads(plan_path.read_text())
    assert plan == [
        {
            "id": stale_report.id,
            "title_before": _STALE_TITLE,
            "subtitle_before": None,
            "title_after": _BUILT_TITLE,
            "subtitle_after": _BUILT_SUBTITLE,
        }
    ]
    assert _get_stored_titles(scratch_session, seeded) == _BEFORE


def test_commit_refuses_after_a_planned_row_changes(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(apply_report_titles_script, "engine", scratch_engine)
    seeded = _seed_reports(scratch_session)
    stale_report, _ = seeded
    stale_changes = [TitleChange(stale_report.id, _STALE_TITLE, None, _BUILT_TITLE, _BUILT_SUBTITLE)]
    scratch_session.get_one(Report, stale_report.id).title = "changed after the plan"
    scratch_session.commit()
    monkeypatch.setattr(apply_report_titles_script, "_get_title_changes", lambda title_rows: stale_changes)

    with pytest.raises(HansardWriteCheckError, match="title changed since the plan was made"):
        apply_report_titles_script.apply_report_titles(is_commit=True, plan_path=None)

    assert _get_stored_titles(scratch_session, seeded) == [("changed after the plan", None), (_CURRENT_TITLE, None)]


def test_commit_on_an_unchanged_state_writes_exactly_the_plan(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(apply_report_titles_script, "engine", scratch_engine)
    seeded = _seed_reports(scratch_session)

    apply_report_titles_script.apply_report_titles(is_commit=True, plan_path=None)

    assert _get_stored_titles(scratch_session, seeded) == _AFTER


def test_commit_refuses_the_protected_local_port_and_writes_nothing(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(apply_report_titles_script, "engine", scratch_engine)
    seeded = _seed_reports(scratch_session)
    monkeypatch.setattr(apply_report_titles_script, "settings", SimpleNamespace(database_url=_PROTECTED_DATABASE_URL))

    with pytest.raises(HansardWriteTargetError, match="5432"):
        apply_report_titles_script.apply_report_titles(is_commit=True, plan_path=None)

    assert _get_stored_titles(scratch_session, seeded) == _BEFORE
