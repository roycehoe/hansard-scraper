import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

import scripts.apply_divisions as apply_divisions_script
from database.division import Division
from database.report import Report
from enums import SpeechKind
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.division_plan import DivisionPlan
from scripts.apply_divisions import apply_divisions
from tests.division_seed import add_division_report, add_division_speech_rows

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_SITTING_DATE = datetime(2018, 1, 10)
_LINE_FIRST = "The House divided: Ayes, 10; Noes, 3."
_LINE_SECOND = "The House divided: Ayes, 20; Noes, 4."
_TOTAL_ONLY = "There are 7 Ayes and 2 Noes."
_FIRST_REPORT_ID = "report-one"
_SECOND_REPORT_ID = "report-two"
_SEEDED_DIVISION_COUNT = 3
_DIVISION_TABLE_NAME = "division"


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


class _VacuumRecorder:
    def __init__(self) -> None:
        self.table_names: list[list[str]] = []

    def __call__(self, session: Session, table_names: list[str]) -> None:
        self.table_names.append(table_names)


def _seed_reports(session: Session) -> tuple[Report, Report]:
    first = add_division_report(session, _FIRST_REPORT_ID, _SITTING_DATE)
    second = add_division_report(session, _SECOND_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        session,
        first,
        [
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
            (SpeechKind.PROCEDURAL, None, _LINE_SECOND),
        ],
    )
    add_division_speech_rows(session, second, [(SpeechKind.SPEECH, None, _TOTAL_ONLY)])
    session.commit()
    return first, second


def _get_division_count(session: Session) -> int:
    session.expire_all()
    return session.exec(select(func.count()).select_from(Division)).one()


def _get_division_ids(session: Session) -> list[int]:
    session.expire_all()
    return [
        division_id
        for division_id in session.exec(select(Division.id).order_by(Division.id)).all()
        if division_id is not None
    ]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_divisions_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_divisions_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_the_plan_file_only(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_divisions([], plan_path, is_commit=False)

    assert log_recorder.messages == [
        "Plan: 3 divisions in 2 reports, 0 unread rows",
        "Divisions by decade and source: 2010s PRINTED_LINE 2, 2010s SPOKEN_TOTAL 1",
        "Unread rows by reason: none",
        "Against stored: 0 kept, 0 updated, 3 added, 0 deleted",
        "Dry run: nothing written",
    ]
    plan = DivisionPlan.model_validate_json(plan_path.read_text())
    assert len(plan.divisions) == _SEEDED_DIVISION_COUNT
    assert _get_division_count(scratch_session) == 0


def test_commit_stores_the_plan_and_a_second_commit_writes_nothing(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        apply_divisions_script, "vacuum_analyze_written_tables", _VacuumRecorder()
    )
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False)

    apply_divisions([], plan_path, is_commit=True)
    first_ids = _get_division_ids(scratch_session)
    apply_divisions([], plan_path, is_commit=True)

    assert len(first_ids) == _SEEDED_DIVISION_COUNT
    assert _get_division_ids(scratch_session) == first_ids
    assert log_recorder.messages[-2] == (
        "Against stored: 3 kept, 0 updated, 0 added, 0 deleted"
    )


def test_commit_refuses_a_plan_that_differs_from_the_reviewed_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    tmp_path: Path,
) -> None:
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False)
    reviewed_plan = json.loads(plan_path.read_text())
    reviewed_plan["divisions"][0]["printed_counts"] = "Changed"
    plan_path.write_text(json.dumps(reviewed_plan))

    with pytest.raises(HansardWriteCheckError, match="differs from the reviewed plan"):
        apply_divisions([], plan_path, is_commit=True)

    assert _get_division_count(scratch_session) == 0


def test_commit_refuses_the_protected_port_before_any_row_is_read(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False)
    monkeypatch.setattr(
        apply_divisions_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_divisions([], plan_path, is_commit=True)

    assert _get_division_count(scratch_session) == 0


def test_report_id_limits_the_plan_to_the_given_reports(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    first, _ = _seed_reports(scratch_session)
    assert first.id is not None
    plan_path = tmp_path / "plan.json"

    apply_divisions([first.id], plan_path, is_commit=False)

    plan = DivisionPlan.model_validate_json(plan_path.read_text())
    assert plan.sprs_report_ids == [_FIRST_REPORT_ID]
    assert {division.sprs_report_id for division in plan.divisions} == {
        _FIRST_REPORT_ID
    }


def test_commit_vacuums_the_division_table(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vacuum_recorder = _VacuumRecorder()
    monkeypatch.setattr(
        apply_divisions_script, "vacuum_analyze_written_tables", vacuum_recorder
    )
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False)

    apply_divisions([], plan_path, is_commit=True)

    assert vacuum_recorder.table_names == [[_DIVISION_TABLE_NAME]]
