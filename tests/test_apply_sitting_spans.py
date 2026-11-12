import re
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, delete, select

import scripts.apply_sitting_spans as apply_sitting_spans_script
from database.attendance import Attendance
from database.sitting import Sitting
from database.sitting_span import SittingSpan
from database.speaker import Speaker
from exceptions import HansardWriteTargetError
from populate.sitting_spans import populate_sitting_spans
from scripts.apply_sitting_spans import apply_sitting_spans

_PARLIAMENT_NUMBER = 14
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_PLAN_LOG = "Plan: 2 sitting spans to add, 0 to update, 0 to delete"
_UPDATE_COLUMNS = ["first_sitting_date", "last_sitting_date", "sitting_count"]


@dataclass(frozen=True)
class _SeededAttendance:
    elected_member: Speaker
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
    location_name: Optional[str],
    is_present: bool = True,
) -> None:
    session.add(Sitting(id=sitting_id, sitting_date=sitting_date))
    session.flush()
    assert speaker.id is not None
    session.add(
        Attendance(
            sitting_id=sitting_id,
            speaker_name=speaker.name,
            is_present=is_present,
            location_name=location_name,
            speaker_id=speaker.id,
        )
    )
    session.flush()


def _seed_attendance(session: Session) -> _SeededAttendance:
    elected_member = _build_speaker("Gerald Giam")
    nominated_member = _build_speaker("Walter Theseira")
    session.add_all([elected_member, nominated_member])
    session.flush()
    _add_attendance(session, 1, "2-1-2020", elected_member, None, is_present=False)
    _add_attendance(session, 2, "3-2-2020", elected_member, "Aljunied GRC")
    _add_attendance(session, 3, "4-2-2020", nominated_member, "Nominated Member")
    session.commit()
    return _SeededAttendance(elected_member, nominated_member)


def _get_stored_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return sorted(
        (
            sitting_span.speaker_id,
            sitting_span.first_sitting_date,
            sitting_span.last_sitting_date,
            sitting_span.sitting_count,
        )
        for sitting_span in session.exec(select(SittingSpan)).all()
    )


def _get_seeded_rows(seeded_attendance: _SeededAttendance) -> list[tuple]:
    return sorted(
        [
            (
                seeded_attendance.elected_member.id,
                date(2020, 1, 2),
                date(2020, 2, 3),
                2,
            ),
            (
                seeded_attendance.nominated_member.id,
                date(2020, 2, 4),
                date(2020, 2, 4),
                1,
            ),
        ]
    )


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_sitting_spans_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_sitting_spans_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_attendance(scratch_session)

    apply_sitting_spans(is_commit=False)

    assert _PLAN_LOG in log_recorder.messages
    assert "2020s: 2 sitting spans" in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_stored_rows(scratch_session) == []


def test_commit_writes_a_span_for_a_member_with_no_division_and_counts_an_absence(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_attendance = _seed_attendance(scratch_session)

    apply_sitting_spans(is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    assert _get_stored_rows(scratch_session) == _get_seeded_rows(seeded_attendance)


def test_commit_starts_the_span_before_the_first_row_that_carries_a_division(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_attendance = _seed_attendance(scratch_session)

    apply_sitting_spans(is_commit=True)

    stored_rows = {row[0]: row for row in _get_stored_rows(scratch_session)}
    assert stored_rows[seeded_attendance.elected_member.id][1] == date(2020, 1, 2)


def test_commit_gives_a_member_with_only_unlinked_attendance_no_span(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    scratch_session.add(Sitting(id=1, sitting_date="2-1-2020"))
    scratch_session.flush()
    scratch_session.add(
        Attendance(sitting_id=1, speaker_name="Nobody Known", is_present=True)
    )
    scratch_session.commit()

    apply_sitting_spans(is_commit=True)

    assert _get_stored_rows(scratch_session) == []


def test_commit_on_a_rerun_leaves_the_same_rows_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_attendance = _seed_attendance(scratch_session)
    apply_sitting_spans(is_commit=True)

    apply_sitting_spans(is_commit=True)

    assert (
        "Plan: 0 sitting spans to add, 0 to update, 0 to delete"
        in log_recorder.messages
    )
    assert _get_stored_rows(scratch_session) == _get_seeded_rows(seeded_attendance)


def test_commit_updates_a_row_whose_bounds_differ_from_the_attendance_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_attendance = _seed_attendance(scratch_session)
    apply_sitting_spans(is_commit=True)
    sitting_span = scratch_session.exec(
        select(SittingSpan).where(
            SittingSpan.speaker_id == seeded_attendance.elected_member.id
        )
    ).one()
    sitting_span.sitting_count = 9
    scratch_session.commit()

    apply_sitting_spans(is_commit=True)

    assert _get_stored_rows(scratch_session) == _get_seeded_rows(seeded_attendance)


def test_commit_deletes_a_span_whose_attendance_rows_are_gone(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_attendance(scratch_session)
    apply_sitting_spans(is_commit=True)
    scratch_session.exec(delete(Attendance))
    scratch_session.commit()

    apply_sitting_spans(is_commit=True)

    assert "Plan: 0 sitting spans to add, 0 to update, 2 to delete" in (
        log_recorder.messages
    )
    assert _get_stored_rows(scratch_session) == []


def test_populate_inserts_and_widens_and_issues_no_delete(
    scratch_engine: Engine, scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_attendance = _seed_attendance(scratch_session)
    apply_sitting_spans(is_commit=True)
    sitting_span = scratch_session.exec(
        select(SittingSpan).where(
            SittingSpan.speaker_id == seeded_attendance.elected_member.id
        )
    ).one()
    sitting_span.first_sitting_date = date(2019, 1, 1)
    scratch_session.commit()
    _add_attendance(
        scratch_session, 4, "3-3-2020", seeded_attendance.elected_member, "Aljunied"
    )
    new_member = _build_speaker("Louis Chua")
    scratch_session.add(new_member)
    scratch_session.flush()
    _add_attendance(scratch_session, 5, "5-3-2020", new_member, "Sengkang GRC")
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
        populate_sitting_spans(scratch_session, [4, 5])
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert _get_stored_rows(scratch_session) == sorted(
        [
            (
                seeded_attendance.elected_member.id,
                date(2019, 1, 1),
                date(2020, 3, 3),
                3,
            ),
            (
                seeded_attendance.nominated_member.id,
                date(2020, 2, 4),
                date(2020, 2, 4),
                1,
            ),
            (new_member.id, date(2020, 3, 5), date(2020, 3, 5), 1),
        ]
    )
    assert any(
        statement.startswith("INSERT INTO sitting_span") for statement in statements
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
        assert statement.startswith("UPDATE sitting_span SET ")
        set_clause = statement.removeprefix("UPDATE sitting_span SET ").split(" WHERE")[
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
        apply_sitting_spans_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_sitting_spans(is_commit=True)

    assert _get_stored_rows(scratch_session) == []


def test_commit_locks_the_table_before_it_reads_the_attendance_rows(
    scratch_engine: Engine, scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_attendance(scratch_session)
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
        apply_sitting_spans(is_commit=True)
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    first_read_index = next(
        i for i, statement in enumerate(statements) if "FROM attendance" in statement
    )
    assert [
        statement
        for statement in statements[:first_read_index]
        if statement.startswith("LOCK TABLE")
    ] == ["LOCK TABLE sitting_span IN SHARE ROW EXCLUSIVE MODE"]
