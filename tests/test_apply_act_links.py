import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_act_links as apply_act_links_script
from crud.act import CRUDAct
from crud.act_history_entry import CRUDActHistoryEntry
from crud.bill import CRUDBill
from crud.bill_report import CRUDBillReport
from enums import ReportType
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.act_link_plan import ActLinkPlan
from scripts.apply_act_links import apply_act_links
from tests.bill_seed import seed_bill_report, write_harvest

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_PASSING_LINE = "Bill read a Third time and passed."


@pytest.fixture(autouse=True)
def _no_bill_title_corrections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apply_act_links_script, "get_bill_title_corrections", list)
    monkeypatch.setattr(apply_act_links_script, "get_hand_kept_bills", list)
    monkeypatch.setattr(apply_act_links_script, "get_hand_kept_act_links", list)


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _seed_reports(session: Session) -> None:
    seed_bill_report(
        session,
        "first-reading",
        ReportType.BILL_INTRODUCTION,
        datetime(2024, 12, 2),
        "Estate Duty Bill",
        ["Bill read a First time."],
    )
    seed_bill_report(
        session,
        "third-reading",
        ReportType.BILL,
        datetime(2025, 1, 15),
        "Estate Duty Bill",
        [_PASSING_LINE],
    )
    seed_bill_report(
        session,
        "adjournment",
        ReportType.BILL,
        datetime(2025, 1, 15),
        "ADJOURNMENT",
        [_PASSING_LINE],
    )


def _get_stored_counts(session: Session) -> tuple[int, int, int, int, int]:
    session.expire_all()
    return (
        CRUDBill(session).get_count(),
        CRUDBillReport(session).get_count(),
        CRUDAct(session).get_count(),
        CRUDActHistoryEntry(session).get_count(),
        CRUDActHistoryEntry(session).get_count_by_bill_id_not_null(),
    )


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_act_links_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_act_links_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_counts_and_writes_the_plan_file_only(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"

    apply_act_links(tmp_path, plan_path, is_commit=False)

    assert log_recorder.messages == [
        "Bills: 1, 1 passed; 2 reports grouped",
        "Skipped: 1 reports whose title names no bill, 1 distinct titles",
        "Bill numbers by source: none; 1 bills without a number",
        "Bill classes: none",
        "Act numbers by source: none; 1 passed bills without an Act number",
        "Split bills merged: 0; eGazette Acts linked to a bill: 0",
        "Acts: 2 read, 1 not fetched, 1 with no Legislative History; 2 entries",
        "Entries by kind: ACT 1, REVISED_EDITION 1",
        "Entries linked by rule: FIRST_READING_DATE 1",
        "Act and Ordinance entries not linked, by kind and decade of first reading: none",
        "Act and Ordinance entries by bill number rule outcome: title rule only 1",
        "Entries by source defect: none",
        "Unparsed entries: 0",
        "Bills: 0 kept, 0 updated, 1 inserted, 0 deleted",
        "Acts: 2 inserted, 0 updated, 0 deleted",
        "Entries: 2 inserted, 0 updated, 0 deleted; 0 linked entries change bill",
        "eGazette supplements: 0 bill links set or cleared",
        "Dry run: nothing written",
    ]
    plan = ActLinkPlan.model_validate_json(plan_path.read_text())
    assert [planned_bill.title_key for planned_bill in plan.bills] == ["estatedutybill"]
    assert _get_stored_counts(scratch_session) == (0, 0, 0, 0, 0)


def test_commit_writes_the_reviewed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_act_links(tmp_path, plan_path, is_commit=False)

    apply_act_links(tmp_path, plan_path, is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    assert _get_stored_counts(scratch_session) == (1, 2, 2, 2, 1)
    assert CRUDBill(scratch_session).get_count_by_is_passed(is_passed=True) == 1


def test_commit_of_the_same_plan_twice_changes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_act_links(tmp_path, plan_path, is_commit=False)
    apply_act_links(tmp_path, plan_path, is_commit=True)
    entry_rows = CRUDActHistoryEntry(scratch_session).get_rows()
    bill_rows = CRUDBill(scratch_session).get_rows()
    log_recorder.messages.clear()

    apply_act_links(tmp_path, plan_path, is_commit=True)

    assert "Bills: 1 kept, 0 updated, 0 inserted, 0 deleted" in log_recorder.messages
    assert "Acts: 0 inserted, 0 updated, 0 deleted" in log_recorder.messages
    assert (
        "Entries: 0 inserted, 0 updated, 0 deleted; 0 linked entries change bill"
        in log_recorder.messages
    )
    assert _get_stored_counts(scratch_session) == (1, 2, 2, 2, 1)
    scratch_session.expire_all()
    assert CRUDActHistoryEntry(scratch_session).get_rows() == entry_rows
    assert CRUDBill(scratch_session).get_rows() == bill_rows


def _write_changed_harvest(directory: Path) -> None:
    (directory / "acts.json").write_text(
        json.dumps(
            [
                {"sso_code": "EDA2025", "title": "Estate Duty Act 2025 (renamed)"},
                {"sso_code": "NEW2026", "title": "New Act 2026"},
            ]
        ),
        encoding="utf8",
    )
    (directory / "NEW2026.txt").write_text("NEW ACT 2026\n\nPart 1\n", encoding="utf8")


def test_commit_applies_a_changed_plan_to_tables_that_hold_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_act_links(tmp_path, plan_path, is_commit=False)
    apply_act_links(tmp_path, plan_path, is_commit=True)
    entry_ids = [row.id for row in CRUDActHistoryEntry(scratch_session).get_rows()]
    _write_changed_harvest(tmp_path)
    apply_act_links(tmp_path, plan_path, is_commit=False)

    apply_act_links(tmp_path, plan_path, is_commit=True)

    assert "Acts: 1 inserted, 1 updated, 1 deleted" in log_recorder.messages
    scratch_session.expire_all()
    assert _get_stored_counts(scratch_session) == (1, 2, 2, 2, 1)
    assert [
        row.id for row in CRUDActHistoryEntry(scratch_session).get_rows()
    ] == entry_ids
    assert sorted(row.title for row in CRUDAct(scratch_session).get_rows()) == [
        "Estate Duty Act 2025 (renamed)",
        "New Act 2026",
    ]


def test_commit_raises_when_the_stored_rows_differ_from_the_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_reports(scratch_session)
    write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_act_links(tmp_path, plan_path, is_commit=False)
    apply_act_links(tmp_path, plan_path, is_commit=True)
    (tmp_path / "acts.json").write_text(
        json.dumps([{"sso_code": "EDA2025", "title": "Renamed"}]), encoding="utf8"
    )
    apply_act_links(tmp_path, plan_path, is_commit=False)
    monkeypatch.setattr(CRUDAct, "update_many", lambda self, act_updates: None)

    with pytest.raises(
        HansardWriteCheckError, match="The stored rows differ from the plan: Stored Act"
    ):
        apply_act_links(tmp_path, plan_path, is_commit=True)

    scratch_session.expire_all()
    assert "Renamed" not in [row.title for row in CRUDAct(scratch_session).get_rows()]


def test_commit_refuses_a_plan_that_differs_from_the_reviewed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_act_links(tmp_path, plan_path, is_commit=False)
    seed_bill_report(
        scratch_session,
        "another-bill",
        ReportType.BILL,
        datetime(2025, 3, 3),
        "Water Bill",
        ["Bill read a First time."],
    )

    with pytest.raises(
        HansardWriteCheckError, match="The plan differs from the reviewed plan"
    ):
        apply_act_links(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (0, 0, 0, 0, 0)


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_reports(scratch_session)
    write_harvest(tmp_path)
    plan_path = tmp_path / "plan.json"
    apply_act_links(tmp_path, plan_path, is_commit=False)
    monkeypatch.setattr(
        apply_act_links_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_act_links(tmp_path, plan_path, is_commit=True)

    assert _get_stored_counts(scratch_session) == (0, 0, 0, 0, 0)
