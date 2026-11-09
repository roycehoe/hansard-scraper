import re
from dataclasses import dataclass, replace
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, delete, select

import populate.seat_holdings as seat_holdings_module
import scripts.apply_seat_holdings as apply_seat_holdings_script
from database.attendance import Attendance
from database.seat_holding import SeatHolding
from database.sitting import Sitting
from database.speaker import Speaker
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from populate.seat_holdings import populate_seat_holdings
from scripts.apply_seat_holdings import apply_seat_holdings
from services.seat_holding import SeatHoldingRecord, build_seat_holding_records

_PARLIAMENT_NUMBER = 14
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_PLAN_LOG = "Plan: 1 seat holdings to add, 0 to update, 0 to delete"
_UPDATE_COLUMNS = ["first_sitting_date", "last_sitting_date", "sitting_count"]


@dataclass(frozen=True)
class _SeededAttendance:
    aljunied_member: Speaker
    nominated_member: Speaker


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _build_speaker(name: str) -> Speaker:
    return Speaker(
        name=name,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )


def _add_attendance(
    session: Session,
    sitting_id: int,
    sitting_date: str,
    speaker: Speaker,
    location_name: str,
) -> None:
    session.add(Sitting(id=sitting_id, sitting_date=sitting_date))
    session.flush()
    assert speaker.id is not None
    session.add(
        Attendance(
            sitting_id=sitting_id,
            speaker_name=speaker.name,
            is_present=True,
            location_name=location_name,
            speaker_id=speaker.id,
        )
    )
    session.flush()


def _seed_attendance(session: Session) -> _SeededAttendance:
    aljunied_member = _build_speaker("Gerald Giam")
    nominated_member = _build_speaker("Walter Theseira")
    session.add_all([aljunied_member, nominated_member])
    session.flush()
    _add_attendance(session, 1, "2-1-2020", aljunied_member, "Aljunied GRC")
    _add_attendance(session, 2, "3-2-2020", aljunied_member, "Aljunied GRC")
    _add_attendance(session, 3, "4-2-2020", nominated_member, "Nominated Member")
    session.commit()
    return _SeededAttendance(aljunied_member, nominated_member)


def _get_stored_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return sorted(
        (
            seat_holding.speaker_id,
            seat_holding.division_key,
            seat_holding.location_name,
            seat_holding.first_sitting_date,
            seat_holding.last_sitting_date,
            seat_holding.sitting_count,
        )
        for seat_holding in session.exec(select(SeatHolding)).all()
    )


def _get_aljunied_rows(seeded_attendance: _SeededAttendance) -> list[tuple]:
    return [
        (
            seeded_attendance.aljunied_member.id,
            "aljunied",
            "Aljunied GRC",
            date(2020, 1, 2),
            date(2020, 2, 3),
            2,
        )
    ]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_seat_holdings_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_seat_holdings_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_attendance(scratch_session)

    apply_seat_holdings(is_commit=False)

    assert _PLAN_LOG in log_recorder.messages
    assert "2020s: 1 seat holdings" in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_stored_rows(scratch_session) == []


def test_commit_writes_the_rows_of_the_divisions_only(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_attendance = _seed_attendance(scratch_session)

    apply_seat_holdings(is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    assert _get_stored_rows(scratch_session) == _get_aljunied_rows(seeded_attendance)


def test_commit_on_a_rerun_leaves_the_same_rows_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_attendance = _seed_attendance(scratch_session)
    apply_seat_holdings(is_commit=True)

    apply_seat_holdings(is_commit=True)

    assert (
        "Plan: 0 seat holdings to add, 0 to update, 0 to delete"
        in log_recorder.messages
    )
    assert _get_stored_rows(scratch_session) == _get_aljunied_rows(seeded_attendance)


def test_commit_updates_a_row_whose_bounds_differ_from_the_attendance_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_attendance = _seed_attendance(scratch_session)
    apply_seat_holdings(is_commit=True)
    seat_holding = scratch_session.exec(select(SeatHolding)).one()
    seat_holding.sitting_count = 9
    scratch_session.commit()

    apply_seat_holdings(is_commit=True)

    assert _get_stored_rows(scratch_session) == _get_aljunied_rows(seeded_attendance)


def test_commit_deletes_a_pair_whose_attendance_rows_are_gone(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_attendance(scratch_session)
    apply_seat_holdings(is_commit=True)
    scratch_session.exec(delete(Attendance))
    scratch_session.commit()

    apply_seat_holdings(is_commit=True)

    assert "Plan: 0 seat holdings to add, 0 to update, 1 to delete" in (
        log_recorder.messages
    )
    assert _get_stored_rows(scratch_session) == []


def test_populate_inserts_and_widens_and_issues_no_delete(
    scratch_engine: Engine, scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_attendance = _seed_attendance(scratch_session)
    apply_seat_holdings(is_commit=True)
    seat_holding = scratch_session.exec(select(SeatHolding)).one()
    seat_holding.first_sitting_date = date(2019, 1, 1)
    scratch_session.commit()
    _add_attendance(
        scratch_session, 4, "3-3-2020", seeded_attendance.aljunied_member, "Aljunied"
    )
    _add_attendance(
        scratch_session, 5, "5-3-2020", seeded_attendance.nominated_member, "Tampines"
    )
    scratch_session.commit()
    statements: list[str] = []

    def record_statement(
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(scratch_engine, "before_cursor_execute", record_statement)
    try:
        populate_seat_holdings(scratch_session, [4, 5])
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert _get_stored_rows(scratch_session) == [
        (
            seeded_attendance.aljunied_member.id,
            "aljunied",
            "Aljunied GRC",
            date(2019, 1, 1),
            date(2020, 3, 3),
            3,
        ),
        (
            seeded_attendance.nominated_member.id,
            "tampines",
            "Tampines",
            date(2020, 3, 5),
            date(2020, 3, 5),
            1,
        ),
    ]
    assert any(
        statement.startswith("INSERT INTO seat_holding") for statement in statements
    )
    assert not [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("DELETE")
    ]
    update_statements = [
        statement for statement in statements if statement.startswith("UPDATE")
    ]
    assert update_statements
    for statement in update_statements:
        assert statement.startswith("UPDATE seat_holding SET ")
        set_clause = statement.removeprefix("UPDATE seat_holding SET ").split(" WHERE")[
            0
        ]
        assert re.findall(r"(\w+)=", set_clause) == _UPDATE_COLUMNS


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_attendance(scratch_session)
    monkeypatch.setattr(
        apply_seat_holdings_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_seat_holdings(is_commit=True)

    assert _get_stored_rows(scratch_session) == []


def test_commit_refuses_a_division_key_that_differs_from_the_sql_fold(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_attendance(scratch_session)

    def build_records_with_wrong_key(
        attendance_seat_rows: list,
    ) -> list[SeatHoldingRecord]:
        return [
            replace(seat_holding_record, division_key="wrong")
            for seat_holding_record in build_seat_holding_records(attendance_seat_rows)
        ]

    monkeypatch.setattr(
        seat_holdings_module, "build_seat_holding_records", build_records_with_wrong_key
    )

    with pytest.raises(HansardWriteCheckError, match="differs from the folded"):
        apply_seat_holdings(is_commit=True)
