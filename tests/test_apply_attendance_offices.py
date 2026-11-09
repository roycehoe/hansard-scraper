import json
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

import scripts.apply_attendance_offices as apply_attendance_offices_script
from crud.attendance_office import CRUDAttendanceOffice
from database.attendance import Attendance
from database.attendance_office import AttendanceOffice
from database.office_printed_range import OfficePrintedRange
from database.sitting import Sitting
from database.speaker import Speaker
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from scripts.apply_attendance_offices import apply_attendance_offices

_OLDER_PARLIAMENT_NUMBER = 8
_NEWER_PARLIAMENT_NUMBER = 14
_OLDER_SITTING_DATE = datetime(1996, 3, 5)
_NEWER_SITTING_DATE = datetime(2025, 4, 3)
_PRIME_MINISTER = "Prime Minister"
_SENIOR_MINISTER_OF_STATE = "Senior Minister of State for Finance"
_PRIME_MINISTER_LINE = "Mr Goh Chok Tong (Marine Parade GRC), Prime Minister.   "
_SENIOR_MINISTER_OF_STATE_LINE = (
    "Mr Chee Hong Tat (Bishan-Toa Payoh), Senior Minister of State for Finance. "
)
_STORED_ATTENDANCE_OFFICE_COUNT = 2
_COMMIT_RUN_COUNT = 2
_PLAN_LOG = (
    "Plan: 2 attendance offices for 2 sittings;"
    " by decade: 1990 1, 2020 1;"
    " by source: AFTER_CONSTITUENCY_BRACKET 2;"
    " 0 entries with no attendance row; 0 duplicate entries"
)
_DRY_RUN_LOG = (
    "Dry run: nothing written. Ranges are built from the stored rows during a commit"
)
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"


@dataclass(frozen=True)
class _SeededSittings:
    goh: Speaker
    chee: Speaker
    older_sitting: Sitting
    newer_sitting: Sitting


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _build_speaker(name: str, parliament_number: int) -> Speaker:
    return Speaker(
        name=name,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=parliament_number,
    )


def _seed_sittings(session: Session) -> _SeededSittings:
    goh = _build_speaker("Goh Chok Tong", _OLDER_PARLIAMENT_NUMBER)
    chee = _build_speaker("Chee Hong Tat", _NEWER_PARLIAMENT_NUMBER)
    older_sitting = Sitting(
        sitting_date="5-3-1996",
        parlement_no=_OLDER_PARLIAMENT_NUMBER,
        markdown_content=f"PRESENT:\n{_PRIME_MINISTER_LINE}\n",
    )
    newer_sitting = Sitting(
        sitting_date="3-4-2025",
        parlement_no=_NEWER_PARLIAMENT_NUMBER,
        attendance_list=json.dumps(
            [
                {
                    "mpName": _SENIOR_MINISTER_OF_STATE_LINE,
                    "attendance": True,
                    "locationName": "Bishan-Toa Payoh",
                }
            ]
        ),
    )
    session.add_all([goh, chee, older_sitting, newer_sitting])
    session.flush()
    assert older_sitting.id is not None
    assert newer_sitting.id is not None
    session.add_all(
        [
            Attendance(
                sitting_id=older_sitting.id,
                speaker_name="Goh Chok Tong",
                is_present=True,
                speaker_id=goh.id,
            ),
            Attendance(
                sitting_id=newer_sitting.id,
                speaker_name="Chee Hong Tat",
                is_present=True,
                speaker_id=chee.id,
            ),
        ]
    )
    session.commit()
    return _SeededSittings(goh, chee, older_sitting, newer_sitting)


def _get_stored_office_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (
            attendance_office.attendance_id,
            attendance_office.office_printed,
            attendance_office.entry_line_printed,
            attendance_office.source,
        )
        for attendance_office in session.exec(
            select(AttendanceOffice).order_by(AttendanceOffice.attendance_id)
        ).all()
    ]


def _get_stored_range_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (
            office_printed_range.speaker_id,
            office_printed_range.office_printed,
            office_printed_range.sitting_count,
            office_printed_range.first_sitting_date,
            office_printed_range.last_sitting_date,
        )
        for office_printed_range in session.exec(
            select(OfficePrintedRange).order_by(OfficePrintedRange.speaker_id)
        ).all()
    ]


def _get_planned_range_rows(seeded_sittings: _SeededSittings) -> list[tuple]:
    return [
        (
            seeded_sittings.goh.id,
            _PRIME_MINISTER,
            1,
            _OLDER_SITTING_DATE,
            _OLDER_SITTING_DATE,
        ),
        (
            seeded_sittings.chee.id,
            _SENIOR_MINISTER_OF_STATE,
            1,
            _NEWER_SITTING_DATE,
            _NEWER_SITTING_DATE,
        ),
    ]


def _get_attendance_office_ids(session: Session) -> dict[str, int]:
    session.expire_all()
    return {
        attendance_office.office_printed: attendance_office.id
        for attendance_office in session.exec(select(AttendanceOffice)).all()
        if attendance_office.id is not None
    }


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_attendance_offices_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_attendance_offices_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sittings(scratch_session)

    apply_attendance_offices([], is_commit=False)

    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == _DRY_RUN_LOG
    assert _get_stored_office_rows(scratch_session) == []
    assert _get_stored_range_rows(scratch_session) == []


def test_commit_writes_the_offices_and_the_ranges(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_sittings = _seed_sittings(scratch_session)

    apply_attendance_offices([], is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    assert [
        office_printed for _, office_printed, _, _ in _get_stored_office_rows(scratch_session)
    ] == [_PRIME_MINISTER, _SENIOR_MINISTER_OF_STATE]
    assert _get_stored_range_rows(scratch_session) == _get_planned_range_rows(
        seeded_sittings
    )


def test_commit_on_a_rerun_leaves_the_same_rows_and_ranges(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_sittings = _seed_sittings(scratch_session)
    apply_attendance_offices([], is_commit=True)
    first_office_rows = _get_stored_office_rows(scratch_session)

    apply_attendance_offices([], is_commit=True)

    assert log_recorder.messages.count(_PLAN_LOG) == _COMMIT_RUN_COUNT
    assert _get_stored_office_rows(scratch_session) == first_office_rows
    assert _get_stored_range_rows(scratch_session) == _get_planned_range_rows(
        seeded_sittings
    )


def test_commit_with_sitting_ids_leaves_other_sittings_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_sittings = _seed_sittings(scratch_session)
    assert seeded_sittings.older_sitting.id is not None
    apply_attendance_offices([], is_commit=True)
    office_ids_before = _get_attendance_office_ids(scratch_session)

    apply_attendance_offices([seeded_sittings.older_sitting.id], is_commit=True)

    office_ids_after = _get_attendance_office_ids(scratch_session)
    assert office_ids_after[_SENIOR_MINISTER_OF_STATE] == office_ids_before[
        _SENIOR_MINISTER_OF_STATE
    ]
    assert office_ids_after[_PRIME_MINISTER] != office_ids_before[_PRIME_MINISTER]
    assert len(office_ids_after) == _STORED_ATTENDANCE_OFFICE_COUNT
    assert _get_stored_range_rows(scratch_session) == _get_planned_range_rows(
        seeded_sittings
    )


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_sittings(scratch_session)
    monkeypatch.setattr(
        apply_attendance_offices_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_attendance_offices([], is_commit=True)

    assert _get_stored_office_rows(scratch_session) == []
    assert _get_stored_range_rows(scratch_session) == []


def test_commit_refuses_stored_rows_that_differ_from_the_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_sittings(scratch_session)
    real_add_many = CRUDAttendanceOffice.add_many

    def add_many_without_the_last_row(
        self: CRUDAttendanceOffice, attendance_offices: list[AttendanceOffice]
    ) -> None:
        real_add_many(self, attendance_offices[:-1])

    monkeypatch.setattr(
        CRUDAttendanceOffice, "add_many", add_many_without_the_last_row
    )

    with pytest.raises(
        HansardWriteCheckError, match="Stored attendance offices by decade"
    ):
        apply_attendance_offices([], is_commit=True)

    assert _get_stored_office_rows(scratch_session) == []
    assert _get_stored_range_rows(scratch_session) == []
