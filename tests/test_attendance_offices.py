import json
from collections import Counter
from dataclasses import dataclass

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, select

from crud.attendance_office import CRUDAttendanceOffice
from database.attendance import Attendance
from database.attendance_office import AttendanceOffice
from database.sitting import Sitting
from database.speaker import Speaker
from enums import AttendanceOfficeSource, OfficeClass
from exceptions import HansardWriteCheckError
from populate.attendance_offices import (
    get_attendance_office_plan,
    populate_attendance_offices,
    write_attendance_office_plan,
)

_OLDER_PARLIAMENT_NUMBER = 8
_NEWER_PARLIAMENT_NUMBER = 14
_STORED_ATTENDANCE_OFFICE_COUNT = 2
_PRIME_MINISTER_LINE = "Mr Goh Chok Tong (Marine Parade GRC), Prime Minister.   "
_SENIOR_MINISTER_OF_STATE_LINE = (
    "Mr Chee Hong Tat (Bishan-Toa Payoh), Senior Minister of State for Finance. "
)
_SENIOR_MINISTER_OF_STATE = "Senior Minister of State for Finance"
_UNLISTED_MEMBER_LINE = "Mr Kwa Soon Bee (Nowhere), Minister for Health."
_DUPLICATE_LINE = "Mr Goh Chok Tong (Marine Parade GRC), Minister for Defence."


@dataclass(frozen=True)
class _SeededSittings:
    older_sitting: Sitting
    newer_sitting: Sitting
    goh_attendance: Attendance
    chee_attendance: Attendance


def _build_speaker(name: str, parliament_number: int) -> Speaker:
    return Speaker(
        name=name,
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=parliament_number,
    )


def _seed_sittings(
    session: Session, older_markdown_lines: list[str]
) -> _SeededSittings:
    goh = _build_speaker("Goh Chok Tong", _OLDER_PARLIAMENT_NUMBER)
    chee = _build_speaker("Chee Hong Tat", _NEWER_PARLIAMENT_NUMBER)
    older_sitting = Sitting(
        sitting_date="5-3-1996",
        parlement_no=_OLDER_PARLIAMENT_NUMBER,
        markdown_content="PRESENT:\n" + "\n".join(older_markdown_lines) + "\n",
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
    goh_attendance = Attendance(
        sitting_id=older_sitting.id,
        speaker_name="Goh Chok Tong",
        is_present=True,
        speaker_id=goh.id,
    )
    chee_attendance = Attendance(
        sitting_id=newer_sitting.id,
        speaker_name="Chee Hong Tat",
        is_present=True,
        speaker_id=chee.id,
    )
    session.add_all([goh_attendance, chee_attendance])
    session.flush()
    return _SeededSittings(
        older_sitting, newer_sitting, goh_attendance, chee_attendance
    )


def _get_sitting_ids(seeded_sittings: _SeededSittings) -> list[int]:
    assert seeded_sittings.older_sitting.id is not None
    assert seeded_sittings.newer_sitting.id is not None
    return [seeded_sittings.older_sitting.id, seeded_sittings.newer_sitting.id]


def _get_stored_attendance_offices(session: Session) -> list[AttendanceOffice]:
    return list(
        session.exec(select(AttendanceOffice).order_by(AttendanceOffice.id)).all()
    )


def test_plan_builds_a_row_for_a_markdown_entry_and_a_list_entry(
    scratch_session: Session,
) -> None:
    seeded_sittings = _seed_sittings(scratch_session, [_PRIME_MINISTER_LINE])

    plan = get_attendance_office_plan(
        scratch_session, _get_sitting_ids(seeded_sittings)
    )

    assert [
        (
            attendance_office.attendance_id,
            attendance_office.office_printed,
            attendance_office.office_class,
            attendance_office.source,
            attendance_office.entry_line_printed,
        )
        for attendance_office in plan.attendance_offices
    ] == [
        (
            seeded_sittings.goh_attendance.id,
            "Prime Minister",
            OfficeClass.PRIME_MINISTER,
            AttendanceOfficeSource.AFTER_CONSTITUENCY_BRACKET,
            _PRIME_MINISTER_LINE,
        ),
        (
            seeded_sittings.chee_attendance.id,
            _SENIOR_MINISTER_OF_STATE,
            OfficeClass.SENIOR_MINISTER_OF_STATE,
            AttendanceOfficeSource.AFTER_CONSTITUENCY_BRACKET,
            _SENIOR_MINISTER_OF_STATE_LINE,
        ),
    ]
    assert plan.decade_to_row_count == Counter({1990: 1, 2020: 1})
    assert plan.source_to_row_count == Counter(
        {AttendanceOfficeSource.AFTER_CONSTITUENCY_BRACKET: 2}
    )
    assert plan.entries_without_attendance_row == 0
    assert plan.duplicate_entries == 0


def test_plan_counts_an_entry_with_no_attendance_row_and_stores_nothing_for_it(
    scratch_session: Session,
) -> None:
    seeded_sittings = _seed_sittings(
        scratch_session, [_PRIME_MINISTER_LINE, _UNLISTED_MEMBER_LINE]
    )

    plan = get_attendance_office_plan(
        scratch_session, _get_sitting_ids(seeded_sittings)
    )

    assert plan.entries_without_attendance_row == 1
    assert len(plan.attendance_offices) == _STORED_ATTENDANCE_OFFICE_COUNT


def test_plan_keeps_the_first_of_two_entries_for_one_attendance_row(
    scratch_session: Session,
) -> None:
    seeded_sittings = _seed_sittings(
        scratch_session, [_PRIME_MINISTER_LINE, _DUPLICATE_LINE]
    )

    plan = get_attendance_office_plan(
        scratch_session, _get_sitting_ids(seeded_sittings)
    )

    assert plan.duplicate_entries == 1
    assert [
        attendance_office.office_printed
        for attendance_office in plan.attendance_offices
    ] == ["Prime Minister", _SENIOR_MINISTER_OF_STATE]


def test_populate_inserts_the_rows_and_issues_no_delete(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    seeded_sittings = _seed_sittings(scratch_session, [_PRIME_MINISTER_LINE])
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
        populate_attendance_offices(scratch_session, _get_sitting_ids(seeded_sittings))
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert any(
        statement.startswith("INSERT INTO attendance_office")
        for statement in statements
    )
    assert not [statement for statement in statements if statement.startswith("DELETE")]
    assert (
        len(_get_stored_attendance_offices(scratch_session))
        == _STORED_ATTENDANCE_OFFICE_COUNT
    )


def test_write_replaces_the_stored_rows_of_the_planned_sittings(
    scratch_session: Session,
) -> None:
    seeded_sittings = _seed_sittings(scratch_session, [_PRIME_MINISTER_LINE])
    sitting_ids = _get_sitting_ids(seeded_sittings)
    populate_attendance_offices(scratch_session, sitting_ids)
    first_stored_ids = [
        attendance_office.id
        for attendance_office in _get_stored_attendance_offices(scratch_session)
    ]

    write_attendance_office_plan(
        scratch_session, get_attendance_office_plan(scratch_session, sitting_ids)
    )

    stored_attendance_offices = _get_stored_attendance_offices(scratch_session)
    assert len(stored_attendance_offices) == _STORED_ATTENDANCE_OFFICE_COUNT
    assert [
        attendance_office.id for attendance_office in stored_attendance_offices
    ] != first_stored_ids


def test_write_with_a_short_delete_raises_and_writes_nothing(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded_sittings = _seed_sittings(scratch_session, [_PRIME_MINISTER_LINE])
    sitting_ids = _get_sitting_ids(seeded_sittings)
    populate_attendance_offices(scratch_session, sitting_ids)
    stored_before = _get_stored_attendance_offices(scratch_session)
    monkeypatch.setattr(
        CRUDAttendanceOffice,
        "delete_by_sitting_ids",
        lambda self, sitting_ids: 0,
    )

    with pytest.raises(HansardWriteCheckError, match="Deleted 0 attendance offices"):
        write_attendance_office_plan(
            scratch_session, get_attendance_office_plan(scratch_session, sitting_ids)
        )

    assert _get_stored_attendance_offices(scratch_session) == stored_before
