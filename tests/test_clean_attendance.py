import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.clean_attendance as clean_attendance_script
from database.attendance import Attendance
from database.sitting import Sitting
from database.speaker import Speaker
from enums import AttendanceCleanupReason
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.attendance_cleanup import (
    AttendanceCleanup,
    AttendanceCorrection,
    AttendanceRemoval,
)
from scripts.clean_attendance import clean_attendance

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_PARLIAMENT_NUMBER = 12
_FRAGMENT_ID = 1
_ALIAS_ID = 2
_LINKED_ID = 3
_PLAN_LOG = "Plan: delete 1 rows, update 1 rows; unlinked rows 2 before, 0 after"


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _get_cleanup() -> AttendanceCleanup:
    return AttendanceCleanup(
        removals=[AttendanceRemoval(id=_FRAGMENT_ID, sitting_id=1, speaker_name="Fragment", is_present=True, reason=AttendanceCleanupReason.NOT_A_NAME)],
        corrections=[
            AttendanceCorrection(
                id=_ALIAS_ID,
                sitting_id=1,
                speaker_name="Wong Lm Ken",
                is_present=True,
                location_name="Alexandra",
                speaker_name_after="Wong Lin Ken",
                location_name_after="Alexandra",
                reason=AttendanceCleanupReason.OCR_ALIAS,
            )
        ],
        speaker_roles=[],
    )


def _get_linked_row_removal_cleanup() -> AttendanceCleanup:
    return AttendanceCleanup(
        removals=[AttendanceRemoval(id=_LINKED_ID, sitting_id=1, speaker_name="Tan Ah Kow", is_present=True, reason=AttendanceCleanupReason.REPEATED_ATTENDEE)],
        corrections=[],
        speaker_roles=[],
    )


def _seed(session: Session) -> None:
    session.add(Sitting(id=1, parlement_no=_PARLIAMENT_NUMBER, sitting_date="14-01-2013"))
    session.add(Speaker(id=1, name="Wong Lin Ken", party="PAP", is_legislative_assembly=True, parliament_number=_PARLIAMENT_NUMBER))
    session.add(Speaker(id=2, name="Tan Ah Kow", party="PAP", is_legislative_assembly=True, parliament_number=_PARLIAMENT_NUMBER))
    session.flush()
    session.add_all(
        [
            Attendance(id=_FRAGMENT_ID, sitting_id=1, speaker_name="Fragment", is_present=True),
            Attendance(id=_ALIAS_ID, sitting_id=1, speaker_name="Wong Lm Ken", is_present=True, location_name="Alexandra"),
            Attendance(id=_LINKED_ID, sitting_id=1, speaker_name="Tan Ah Kow", is_present=True, speaker_id=2),
        ]
    )
    session.commit()


def _get_attendance_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (attendance.id, attendance.speaker_name, attendance.location_name, attendance.speaker_id)
        for attendance in session.exec(select(Attendance).order_by(Attendance.id)).all()
    ]


@pytest.fixture
def log_recorder(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(clean_attendance_script, "engine", scratch_engine)
    monkeypatch.setattr(clean_attendance_script, "logger", recorder)
    monkeypatch.setattr(clean_attendance_script, "get_attendance_cleanup", _get_cleanup)
    return recorder


def test_dry_run_logs_the_plan_writes_the_plan_file_and_changes_no_row(scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path) -> None:
    _seed(scratch_session)
    rows_before = _get_attendance_rows(scratch_session)
    plan_path = tmp_path / "plan.json"

    clean_attendance(is_commit=False, plan_path=plan_path)

    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    plan = json.loads(plan_path.read_text())
    assert plan["removal_id_to_reason"] == {str(_FRAGMENT_ID): "NOT_A_NAME"}
    assert [(update["id"], update["speaker_name"], update["speaker_id"]) for update in plan["updates"]] == [(_ALIAS_ID, "Wong Lin Ken", 1)]
    assert _get_attendance_rows(scratch_session) == rows_before


def test_commit_on_unchanged_state_writes_exactly_the_plan(scratch_session: Session, log_recorder: _LogRecorder) -> None:
    _seed(scratch_session)

    clean_attendance(is_commit=True, plan_path=None)

    assert _PLAN_LOG in log_recorder.messages
    assert _get_attendance_rows(scratch_session) == [(_ALIAS_ID, "Wong Lin Ken", "Alexandra", 1), (_LINKED_ID, "Tan Ah Kow", None, 2)]


def test_commit_refuses_and_writes_nothing_when_the_cleanup_removes_the_only_row_of_a_linked_speaker(
    scratch_session: Session, log_recorder: _LogRecorder, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(scratch_session)
    rows_before = _get_attendance_rows(scratch_session)
    monkeypatch.setattr(clean_attendance_script, "get_attendance_cleanup", _get_linked_row_removal_cleanup)

    with pytest.raises(HansardWriteCheckError, match="removed the only row of a speaker in a sitting"):
        clean_attendance(is_commit=True, plan_path=None)

    assert _get_attendance_rows(scratch_session) == rows_before


def test_commit_refuses_the_protected_port_before_any_row_is_written(scratch_session: Session, log_recorder: _LogRecorder, monkeypatch: pytest.MonkeyPatch) -> None:
    _seed(scratch_session)
    rows_before = _get_attendance_rows(scratch_session)
    monkeypatch.setattr(clean_attendance_script, "settings", SimpleNamespace(database_url=_PROTECTED_DATABASE_URL))

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        clean_attendance(is_commit=True, plan_path=None)

    assert _get_attendance_rows(scratch_session) == rows_before
