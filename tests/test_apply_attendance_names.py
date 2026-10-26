import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_attendance_names as apply_attendance_names_script
from crud.attendance import CRUDAttendance
from database.attendance import Attendance
from database.sitting import Sitting
from database.speaker import Speaker
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.constituency_names import ConstituencyNames

_PROTECTED_PORT_URL = "postgresql://u:p@localhost:5432/x"
_PRINTED_NAME = "Lee Kuan Yew"
_STORED_NAME = "Lee Kuan Yew  "


def _seed_misspaced_attendance(session: Session) -> None:
    session.add(Speaker(id=1, name=_PRINTED_NAME, party="PAP", is_legislative_assembly=False, parliament_number=1))
    session.add(
        Sitting(
            id=1, parlement_no=1, sitting_date="1-1-1960",
            attendance_list=json.dumps([{"mpName": f"Mr {_PRINTED_NAME} (Tanjong Pagar)", "attendance": True}]),
        )
    )
    session.flush()
    session.add(Attendance(id=1, sitting_id=1, speaker_name=_STORED_NAME, is_present=True, location_name="Tanjong Pagar", speaker_id=1))
    session.commit()


def _get_speaker_names(session: Session) -> dict[int, str | None]:
    session.expire_all()
    return {attendance.id: attendance.speaker_name for attendance in CRUDAttendance(session).get_all() if attendance.id is not None}


@pytest.fixture(autouse=True)
def _use_scratch_database(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apply_attendance_names_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_attendance_names_script, "get_constituency_names", lambda: ConstituencyNames(names=[], rows=[]))


def test_dry_run_writes_the_plan_and_changes_no_row(scratch_session: Session, tmp_path: Path) -> None:
    _seed_misspaced_attendance(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_attendance_names_script.apply_attendance_names(False, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [(change["id"], change["speaker_name_before"], change["speaker_name_after"], change["speaker_id"]) for change in plan] == [
        (1, _STORED_NAME, _PRINTED_NAME, 1)
    ]
    assert _get_speaker_names(scratch_session) == {1: _STORED_NAME}


def test_commit_is_refused_on_the_protected_port_and_writes_nothing(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_misspaced_attendance(scratch_session)
    monkeypatch.setattr(apply_attendance_names_script, "settings", SimpleNamespace(database_url=_PROTECTED_PORT_URL))

    with pytest.raises(HansardWriteTargetError):
        apply_attendance_names_script.apply_attendance_names(True, None)

    assert _get_speaker_names(scratch_session) == {1: _STORED_NAME}


def test_commit_refuses_a_short_update_count_and_keeps_the_rows(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_misspaced_attendance(scratch_session)
    real_set_speaker_names_bulk = CRUDAttendance.set_speaker_names_bulk

    def set_speaker_names_bulk_one_short(self: CRUDAttendance, attendance_id_to_speaker_name: dict[int, str]) -> int:
        return real_set_speaker_names_bulk(self, attendance_id_to_speaker_name) - 1

    monkeypatch.setattr(CRUDAttendance, "set_speaker_names_bulk", set_speaker_names_bulk_one_short)

    with pytest.raises(HansardWriteCheckError, match="Updated 0 attendance rows, planned 1"):
        apply_attendance_names_script.apply_attendance_names(True, None)

    assert _get_speaker_names(scratch_session) == {1: _STORED_NAME}


def test_commit_refuses_after_a_planned_row_changes(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_misspaced_attendance(scratch_session)
    stale_changes = apply_attendance_names_script._get_planned_changes(scratch_session)
    scratch_session.get_one(Attendance, 1).speaker_name = "changed after the plan"
    scratch_session.commit()
    monkeypatch.setattr(apply_attendance_names_script, "_get_planned_changes", lambda session: stale_changes)

    with pytest.raises(HansardWriteCheckError, match="Attendance row 1 holds"):
        apply_attendance_names_script.apply_attendance_names(True, None)

    assert _get_speaker_names(scratch_session) == {1: "changed after the plan"}


def test_commit_on_an_unchanged_state_writes_exactly_the_plan(scratch_session: Session, tmp_path: Path) -> None:
    _seed_misspaced_attendance(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_attendance_names_script.apply_attendance_names(True, plan_path)

    assert len(json.loads(plan_path.read_text())) == 1
    assert _get_speaker_names(scratch_session) == {1: _PRINTED_NAME}
    scratch_session.expire_all()
    attendance = CRUDAttendance(scratch_session).get_all()[0]
    assert (attendance.sitting_id, attendance.is_present, attendance.location_name, attendance.speaker_id) == (1, True, "Tanjong Pagar", 1)
    apply_attendance_names_script.apply_attendance_names(True, plan_path)
    assert json.loads(plan_path.read_text()) == []
