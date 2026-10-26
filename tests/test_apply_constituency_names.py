import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session

import scripts.apply_constituency_names as apply_constituency_names_script
from crud.attendance import CRUDAttendance
from database.attendance import Attendance
from database.sitting import Sitting
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.constituency_names import ConstituencyName, ConstituencyNames

_PROTECTED_PORT_URL = "postgresql://u:p@localhost:5432/x"


def _get_test_constituency_names() -> ConstituencyNames:
    return ConstituencyNames(names=[ConstituencyName(printed="Aijunied", constituency="Aljunied")], rows=[])


def _seed_attendance_rows(session: Session) -> None:
    session.add(Sitting(id=1, parlement_no=9, sitting_date="1-1-2000"))
    session.flush()
    session.add_all(
        [
            Attendance(id=1, sitting_id=1, speaker_name="Ann", is_present=True, location_name="Aijunied"),
            Attendance(id=2, sitting_id=1, speaker_name="Bob", is_present=True, location_name="Bukit Timah"),
            Attendance(id=3, sitting_id=1, speaker_name="Cat", is_present=False, location_name=None),
        ]
    )
    session.commit()


def _get_location_names(session: Session) -> dict[int, str | None]:
    session.expire_all()
    return {attendance.id: attendance.location_name for attendance in CRUDAttendance(session).get_all() if attendance.id is not None}


@pytest.fixture(autouse=True)
def _use_scratch_database(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apply_constituency_names_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_constituency_names_script, "get_constituency_names", _get_test_constituency_names)


def test_dry_run_writes_the_plan_and_changes_no_row(scratch_session: Session, tmp_path: Path) -> None:
    _seed_attendance_rows(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_constituency_names_script.apply_constituency_names(False, plan_path)

    plan = json.loads(plan_path.read_text())
    assert [(change["id"], change["location_name_before"], change["location_name_after"]) for change in plan] == [(1, "Aijunied", "Aljunied")]
    assert _get_location_names(scratch_session) == {1: "Aijunied", 2: "Bukit Timah", 3: None}


def test_commit_is_refused_on_the_protected_port_and_writes_nothing(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_attendance_rows(scratch_session)
    monkeypatch.setattr(apply_constituency_names_script, "settings", SimpleNamespace(database_url=_PROTECTED_PORT_URL))

    with pytest.raises(HansardWriteTargetError):
        apply_constituency_names_script.apply_constituency_names(True, None)

    assert _get_location_names(scratch_session) == {1: "Aijunied", 2: "Bukit Timah", 3: None}


def test_commit_refuses_a_short_update_count_and_keeps_the_rows(scratch_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed_attendance_rows(scratch_session)
    real_set_location_names_bulk = CRUDAttendance.set_location_names_bulk

    def set_location_names_bulk_one_short(self: CRUDAttendance, attendance_id_to_location_name: dict[int, str]) -> int:
        return real_set_location_names_bulk(self, attendance_id_to_location_name) - 1

    monkeypatch.setattr(CRUDAttendance, "set_location_names_bulk", set_location_names_bulk_one_short)

    with pytest.raises(HansardWriteCheckError, match="Updated 0 attendance rows, planned 1"):
        apply_constituency_names_script.apply_constituency_names(True, None)

    assert _get_location_names(scratch_session) == {1: "Aijunied", 2: "Bukit Timah", 3: None}


def test_commit_on_an_unchanged_state_writes_exactly_the_plan(scratch_session: Session, tmp_path: Path) -> None:
    _seed_attendance_rows(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_constituency_names_script.apply_constituency_names(True, plan_path)

    assert len(json.loads(plan_path.read_text())) == 1
    assert _get_location_names(scratch_session) == {1: "Aljunied", 2: "Bukit Timah", 3: None}
    apply_constituency_names_script.apply_constituency_names(True, plan_path)
    assert json.loads(plan_path.read_text()) == []
    assert _get_location_names(scratch_session) == {1: "Aljunied", 2: "Bukit Timah", 3: None}
