import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.apply_coverage_refill as apply_coverage_refill_script
from database.hansard_website_response import HansardWebsiteResponse
from database.report import Report
from database.speech import Speech
from enums import ReportType, ReportVersion
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.hansard_search_result import HansardSearchResult
from services.hansard_website import build_hansard_website_response
from services.report import build_report

_REPORT_ID = "coverage-refill-report"
_TOPIC_CONTENT = "<p><strong>Mr Speaker:</strong> Order.</p><p><strong>Mr Tan:</strong> Sir, I agree.</p>"
_SPEECH_COUNT = 2
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_SEARCH_RESULT = {
    "volumeNo": "14",
    "reportType": ReportType.MOTION,
    "reportVersion": ReportVersion.SPRS3,
    "title": "Coverage Refill Motion",
    "columnStart": "1",
    "columnEnd": "2",
    "parlNo": "14",
    "reportId": _REPORT_ID,
    "sno": "1",
    "sittingDate": "02-04-2025",
    "htmlFileName": None,
}


def _fetch_topic_content(report_id: str, html_file_name: str | None, report_version: str) -> str:
    return _TOPIC_CONTENT


def _fail_fetch_topic_content(report_id: str, html_file_name: str | None, report_version: str) -> str:
    raise AssertionError("Commit must not fetch from SPRS")


def _write_hits(tmp_path: Path) -> Path:
    hits_path = tmp_path / "hits.json"
    hits_path.write_text(json.dumps([_SEARCH_RESULT]))
    return hits_path


def _get_row_counts(scratch_session: Session) -> tuple[int, int, int]:
    scratch_session.expire_all()
    return tuple(len(scratch_session.exec(select(table)).all()) for table in (HansardWebsiteResponse, Report, Speech))


def test_dry_run_writes_the_plan_and_changes_no_row(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_coverage_refill_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_coverage_refill_script, "_fetch_topic_content", _fetch_topic_content)
    plan_path = tmp_path / "plan.json"

    apply_coverage_refill_script.apply_coverage_refill(plan_path, _write_hits(tmp_path), [], is_commit=False)

    plan = json.loads(plan_path.read_text())
    assert [fetched_hit["search_result"]["reportId"] for fetched_hit in plan["fetched_hits"]] == [_REPORT_ID]
    assert plan["fetched_hits"][0]["content"] == _TOPIC_CONTENT
    assert plan["fetched_hits"][0]["speech_count"] == _SPEECH_COUNT
    assert plan["fetched_reports"] == []
    assert _get_row_counts(scratch_session) == (0, 0, 0)


def test_commit_refuses_after_a_planned_hit_is_stored(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_coverage_refill_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_coverage_refill_script, "_fetch_topic_content", _fetch_topic_content)
    plan_path = tmp_path / "plan.json"
    apply_coverage_refill_script.apply_coverage_refill(plan_path, _write_hits(tmp_path), [], is_commit=False)
    scratch_session.add(build_report(build_hansard_website_response(HansardSearchResult.model_validate(_SEARCH_RESULT), None)))
    scratch_session.commit()

    with pytest.raises(HansardWriteCheckError, match="already stored as reports"):
        apply_coverage_refill_script.apply_coverage_refill(plan_path, None, [], is_commit=True)

    assert _get_row_counts(scratch_session) == (0, 1, 0)


def test_commit_on_an_unchanged_state_writes_exactly_the_plan(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_coverage_refill_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_coverage_refill_script, "_fetch_topic_content", _fetch_topic_content)
    plan_path = tmp_path / "plan.json"
    apply_coverage_refill_script.apply_coverage_refill(plan_path, _write_hits(tmp_path), [], is_commit=False)
    monkeypatch.setattr(apply_coverage_refill_script, "_fetch_topic_content", _fail_fetch_topic_content)

    apply_coverage_refill_script.apply_coverage_refill(plan_path, None, [], is_commit=True)

    assert _get_row_counts(scratch_session) == (1, 1, _SPEECH_COUNT)
    stored_report = scratch_session.exec(select(Report)).one()
    assert stored_report.report_id == _REPORT_ID
    assert stored_report.content == _TOPIC_CONTENT


def test_commit_refuses_the_protected_local_port_and_writes_nothing(
    scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(apply_coverage_refill_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_coverage_refill_script, "_fetch_topic_content", _fetch_topic_content)
    plan_path = tmp_path / "plan.json"
    apply_coverage_refill_script.apply_coverage_refill(plan_path, _write_hits(tmp_path), [], is_commit=False)
    monkeypatch.setattr(apply_coverage_refill_script, "settings", SimpleNamespace(database_url=_PROTECTED_DATABASE_URL))

    with pytest.raises(HansardWriteTargetError, match="5432"):
        apply_coverage_refill_script.apply_coverage_refill(plan_path, None, [], is_commit=True)

    assert _get_row_counts(scratch_session) == (0, 0, 0)
