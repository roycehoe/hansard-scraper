import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.fill_sitting_numbers as fill_sitting_numbers_script
from crud.sitting import CRUDSitting
from database.report import Report
from database.sitting import Sitting
from exceptions import HansardWriteCheckError, HansardWriteTargetError

_HEADER_SESSION_NUMBER = 2
_HEADER_SITTING_NUMBER = 14
_STORED_SITTING_NUMBER = 9


def _get_header(session_number: Optional[int], sitting_number: Optional[int]) -> str:
    lines = []
    if session_number is not None:
        lines.append(f"Session No: | {session_number}")
    if sitting_number is not None:
        lines.append(f"Sitting No: | {sitting_number}")
    return "\n".join(lines)


def _add_sitting(session: Session, session_no: Optional[int], sitting_no: Optional[int], markdown_content: str) -> Sitting:
    sitting = Sitting(sitting_date="22-10-2007", session_no=session_no, sitting_no=sitting_no, markdown_content=markdown_content)
    session.add(sitting)
    session.commit()
    session.refresh(sitting)
    return sitting


def _add_report(session: Session, report_id: str, markdown_content: str) -> Report:
    report = Report(
        volume_number=83, parliament_number=11, sitting_date=datetime(2007, 10, 22), speech_number=1, original_title="Bill", title="Bill",
        report_id=report_id, report_type="bill", markdown_content=markdown_content, report_version="sprs2",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _use_scratch(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fill_sitting_numbers_script, "engine", scratch_engine)


def _get_sitting_numbers(session: Session) -> list[tuple[Optional[int], Optional[int]]]:
    session.expire_all()
    return [(sitting.session_no, sitting.sitting_no) for sitting in session.exec(select(Sitting).order_by(Sitting.id)).all()]


def _get_report_sitting_numbers(session: Session) -> list[Optional[int]]:
    session.expire_all()
    return [report.sitting_number for report in session.exec(select(Report).order_by(Report.id)).all()]


def test_dry_run_writes_the_plan_and_no_rows(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    sitting = _add_sitting(scratch_session, None, None, _get_header(_HEADER_SESSION_NUMBER, _HEADER_SITTING_NUMBER))
    report = _add_report(scratch_session, "r1", "no header")
    plan_path = tmp_path / "plan.json"

    fill_sitting_numbers_script.fill_sitting_numbers(False, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [(fill["id"], fill["number"], fill["source"]) for fill in plan["session_fills"]] == [(sitting.id, _HEADER_SESSION_NUMBER, "sitting header")]
    assert [(fill["id"], fill["number"], fill["source"]) for fill in plan["sitting_fills"]] == [(sitting.id, _HEADER_SITTING_NUMBER, "sitting header")]
    assert [(fill["id"], fill["number"], fill["source"]) for fill in plan["report_fills"]] == [(report.id, _HEADER_SITTING_NUMBER, "sitting of the same date")]
    assert _get_sitting_numbers(scratch_session) == [(None, None)]
    assert _get_report_sitting_numbers(scratch_session) == [None]


def test_commit_leaves_a_stored_sitting_number_that_differs_from_the_header(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _add_sitting(scratch_session, None, _STORED_SITTING_NUMBER, _get_header(_HEADER_SESSION_NUMBER, _HEADER_SITTING_NUMBER))
    plan_path = tmp_path / "plan.json"

    fill_sitting_numbers_script.fill_sitting_numbers(True, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [disagreement["reason"] for disagreement in plan["disagreements"]] == [f"sitting_no {_STORED_SITTING_NUMBER}, header {_HEADER_SITTING_NUMBER}"]
    assert plan["sitting_fills"] == []
    assert _get_sitting_numbers(scratch_session) == [(_HEADER_SESSION_NUMBER, _STORED_SITTING_NUMBER)]


def test_commit_writes_exactly_the_plan_and_a_second_commit_changes_nothing(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    _add_sitting(scratch_session, None, None, _get_header(_HEADER_SESSION_NUMBER, _HEADER_SITTING_NUMBER))
    _add_sitting(scratch_session, None, None, "")
    _add_report(scratch_session, "r1", "no header")
    _add_report(scratch_session, "r2", _get_header(None, 3))

    fill_sitting_numbers_script.fill_sitting_numbers(True, None)

    assert _get_sitting_numbers(scratch_session) == [(_HEADER_SESSION_NUMBER, _HEADER_SITTING_NUMBER), (None, None)]
    assert _get_report_sitting_numbers(scratch_session) == [_HEADER_SITTING_NUMBER, 3]
    plan_path = tmp_path / "plan.json"
    fill_sitting_numbers_script.fill_sitting_numbers(True, plan_path)
    plan = json.loads(plan_path.read_text())
    assert plan["session_fills"] == plan["sitting_fills"] == plan["report_fills"] == []
    assert _get_sitting_numbers(scratch_session) == [(_HEADER_SESSION_NUMBER, _HEADER_SITTING_NUMBER), (None, None)]


def test_commit_refuses_the_protected_local_port(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    monkeypatch.setattr(fill_sitting_numbers_script, "settings", SimpleNamespace(database_url="postgresql://u:p@localhost:5432/x"))
    _add_sitting(scratch_session, None, None, _get_header(_HEADER_SESSION_NUMBER, _HEADER_SITTING_NUMBER))

    with pytest.raises(HansardWriteTargetError):
        fill_sitting_numbers_script.fill_sitting_numbers(True, None)

    assert _get_sitting_numbers(scratch_session) == [(None, None)]


def test_commit_refuses_a_short_sitting_number_write_and_rolls_back_the_session_numbers(scratch_engine: Engine, scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _use_scratch(scratch_engine, monkeypatch)
    monkeypatch.setattr(CRUDSitting, "set_sitting_numbers_bulk", lambda self, number_by_id: 0)
    _add_sitting(scratch_session, None, None, _get_header(_HEADER_SESSION_NUMBER, _HEADER_SITTING_NUMBER))

    with pytest.raises(HansardWriteCheckError, match="Updated 0 sitting numbers, planned 1"):
        fill_sitting_numbers_script.fill_sitting_numbers(True, None)

    assert _get_sitting_numbers(scratch_session) == [(None, None)]
