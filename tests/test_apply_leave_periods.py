import json
from collections import Counter
from datetime import date
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, col, select

import scripts.apply_leave_periods as apply_leave_periods_script
from crud.leave_period_printing import CRUDLeavePeriodPrinting
from database.attendance import Attendance
from database.leave_period import LeavePeriod, LeavePeriodPrinting
from database.sitting import Sitting
from database.speaker import Speaker
from enums import (
    LeaveEntryFormat,
    LeaveNameSource,
    LeaveOfficeSource,
    LeaveSpeakerLinkSource,
    LeaveYearSource,
)
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from populate.leave_periods import populate_leave_periods
from scripts.apply_leave_periods import apply_leave_periods
from utils.leave_entry import LeaveDates, LeaveEntry

_PARLIAMENT_NUMBER = 14
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_NAMED_KEY = "mr lee hsien loong|2020-03-05|2020-03-07"
_UNMERGED_KEY = "entry|3|1"
_PLAN_LOG = "Plan: 4 printings in 2 periods"
_BLANK_ROW_ORDINAL = 2
_OFFICE_PRINTED = "Prime Minister"
_UNOFFICED_ROW_ORDINAL = 2
_UNLINKED_ROW_ORDINAL = 3


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _build_permission_list(*names: Optional[str]) -> str:
    return json.dumps(
        [
            {"mpName": name, "from": "5 Mar", "to": "7 Mar", "endDtFlag": False}
            for name in names
        ]
    )


def _build_sitting(
    sitting_id: int, sitting_date: str, permission_list: Optional[str]
) -> Sitting:
    return Sitting(
        id=sitting_id,
        sitting_date=sitting_date,
        parlement_no=_PARLIAMENT_NUMBER,
        ptba_list=permission_list,
        ptba_from="2020",
        ptba_to="2020",
    )


def _seed_sittings(session: Session) -> Speaker:
    lee = Speaker(
        name="Lee Hsien Loong",
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    session.add(lee)
    session.add_all(
        [
            _build_sitting(
                1,
                "6-3-2020",
                _build_permission_list("Mr Lee Hsien Loong", None),
            ),
            _build_sitting(
                2, "7-3-2020", _build_permission_list("Mr  Lee Hsien Loong")
            ),
            _build_sitting(3, "10-3-2020", _build_permission_list(None)),
            _build_sitting(4, "11-3-2020", None),
        ]
    )
    session.commit()
    return lee


def _get_stored_printings(session: Session) -> list[tuple]:
    session.expire_all()
    period_id_to_key = {
        leave_period.id: leave_period.period_key
        for leave_period in session.exec(select(LeavePeriod)).all()
    }
    return sorted(
        (
            leave_period_printing.sitting_id,
            leave_period_printing.ordinal,
            period_id_to_key[leave_period_printing.leave_period_id],
            leave_period_printing.printed_name,
            leave_period_printing.carried_name,
            leave_period_printing.name_source,
            leave_period_printing.speaker_id,
            leave_period_printing.speaker_link_source,
            leave_period_printing.is_covering_sitting,
        )
        for leave_period_printing in session.exec(select(LeavePeriodPrinting)).all()
    )


def _get_stored_periods(session: Session) -> list[tuple]:
    session.expire_all()
    return sorted(
        (
            leave_period.period_key,
            leave_period.name,
            leave_period.start_date,
            leave_period.end_date,
        )
        for leave_period in session.exec(select(LeavePeriod)).all()
    )


def _get_expected_printings(lee: Speaker) -> list[tuple]:
    return [
        (
            1,
            1,
            _NAMED_KEY,
            "Mr Lee Hsien Loong",
            None,
            LeaveNameSource.PRINTED,
            lee.id,
            LeaveSpeakerLinkSource.ROSTER_NAME,
            True,
        ),
        (
            1,
            2,
            _NAMED_KEY,
            None,
            "Mr Lee Hsien Loong",
            LeaveNameSource.CARRIED_FROM_ROW_ABOVE,
            lee.id,
            LeaveSpeakerLinkSource.ROSTER_NAME,
            True,
        ),
        (
            2,
            1,
            _NAMED_KEY,
            "Mr  Lee Hsien Loong",
            None,
            LeaveNameSource.PRINTED,
            lee.id,
            LeaveSpeakerLinkSource.ROSTER_NAME,
            True,
        ),
        (
            3,
            1,
            _UNMERGED_KEY,
            None,
            None,
            LeaveNameSource.NONE,
            None,
            None,
            False,
        ),
    ]


_EXPECTED_PERIODS = [
    (_UNMERGED_KEY, None, date(2020, 3, 5), date(2020, 3, 7)),
    (_NAMED_KEY, "Mr Lee Hsien Loong", date(2020, 3, 5), date(2020, 3, 7)),
]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_leave_periods_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_leave_periods_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sittings(scratch_session)

    apply_leave_periods(is_commit=False)

    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_stored_printings(scratch_session) == []
    assert _get_stored_periods(scratch_session) == []


def test_commit_writes_the_printings_and_the_periods(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    lee = _seed_sittings(scratch_session)

    apply_leave_periods(is_commit=True)

    assert log_recorder.messages[-1] == "Committed"
    assert _get_stored_printings(scratch_session) == _get_expected_printings(lee)
    assert _get_stored_periods(scratch_session) == _EXPECTED_PERIODS


def test_a_period_printed_at_two_sittings_is_one_row_with_the_first_name(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sittings(scratch_session)

    apply_leave_periods(is_commit=True)

    named_period = scratch_session.exec(
        select(LeavePeriod).where(LeavePeriod.period_key == _NAMED_KEY)
    ).one()
    printing_sitting_ids = [
        leave_period_printing.sitting_id
        for leave_period_printing in scratch_session.exec(
            select(LeavePeriodPrinting).where(
                LeavePeriodPrinting.leave_period_id == named_period.id
            )
        ).all()
    ]
    assert named_period.name == "Mr Lee Hsien Loong"
    assert sorted(printing_sitting_ids) == [1, 1, 2]


def test_a_blank_row_merges_with_a_named_printing_of_the_same_dates(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sittings(scratch_session)

    apply_leave_periods(is_commit=True)

    blank_printing = scratch_session.exec(
        select(LeavePeriodPrinting)
        .where(LeavePeriodPrinting.sitting_id == 1)
        .where(LeavePeriodPrinting.ordinal == _BLANK_ROW_ORDINAL)
    ).one()
    named_printing = scratch_session.exec(
        select(LeavePeriodPrinting)
        .where(LeavePeriodPrinting.sitting_id == 1)
        .where(LeavePeriodPrinting.ordinal == 1)
    ).one()
    assert blank_printing.leave_period_id == named_printing.leave_period_id


def test_a_blank_first_row_is_stored_with_no_name_and_does_not_merge(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sittings(scratch_session)

    apply_leave_periods(is_commit=True)

    unmerged_period = scratch_session.exec(
        select(LeavePeriod).where(LeavePeriod.period_key == _UNMERGED_KEY)
    ).one()
    assert unmerged_period.name is None
    assert (
        scratch_session.exec(
            select(LeavePeriodPrinting).where(
                LeavePeriodPrinting.leave_period_id == unmerged_period.id
            )
        )
        .one()
        .name_source
        == LeaveNameSource.NONE
    )


def test_a_second_commit_leaves_equal_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    lee = _seed_sittings(scratch_session)
    apply_leave_periods(is_commit=True)

    apply_leave_periods(is_commit=True)

    assert _get_stored_printings(scratch_session) == _get_expected_printings(lee)
    assert _get_stored_periods(scratch_session) == _EXPECTED_PERIODS


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_sittings(scratch_session)
    monkeypatch.setattr(
        apply_leave_periods_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_leave_periods(is_commit=True)

    assert _get_stored_printings(scratch_session) == []


def _get_statements_of_apply_leave_periods(
    scratch_engine: Engine, is_commit: bool
) -> list[str]:
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
        apply_leave_periods(is_commit=is_commit)
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)
    return statements


def test_commit_locks_both_tables_before_it_reads_the_sittings(
    scratch_engine: Engine, scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sittings(scratch_session)

    statements = _get_statements_of_apply_leave_periods(scratch_engine, is_commit=True)

    first_read_index = next(
        i for i, statement in enumerate(statements) if "FROM sitting" in statement
    )
    assert [
        statement
        for statement in statements[:first_read_index]
        if statement.startswith("LOCK TABLE")
    ] == [
        "LOCK TABLE leave_period IN SHARE ROW EXCLUSIVE MODE",
        "LOCK TABLE leave_period_printing IN SHARE ROW EXCLUSIVE MODE",
    ]


def test_a_dry_run_takes_no_lock(
    scratch_engine: Engine, scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sittings(scratch_session)

    statements = _get_statements_of_apply_leave_periods(scratch_engine, is_commit=False)

    assert not any(statement.startswith("LOCK TABLE") for statement in statements)


def test_populate_inserts_against_an_existing_period_and_issues_no_delete_or_update(
    scratch_engine: Engine, scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    lee = _seed_sittings(scratch_session)
    apply_leave_periods(is_commit=True)
    scratch_session.add(
        _build_sitting(5, "12-3-2020", _build_permission_list("Mr Lee Hsien Loong"))
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
        populate_leave_periods(scratch_session, [5])
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert _get_stored_periods(scratch_session) == _EXPECTED_PERIODS
    assert _get_stored_printings(scratch_session) == sorted(
        _get_expected_printings(lee)
        + [
            (
                5,
                1,
                _NAMED_KEY,
                "Mr Lee Hsien Loong",
                None,
                LeaveNameSource.PRINTED,
                lee.id,
                LeaveSpeakerLinkSource.ROSTER_NAME,
                False,
            )
        ]
    )
    assert any(
        statement.startswith("INSERT INTO leave_period_printing")
        for statement in statements
    )
    assert not [
        statement
        for statement in statements
        if statement.startswith("INSERT INTO leave_period ")
    ]
    assert not [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(("DELETE", "UPDATE"))
    ]


def test_commit_refuses_stored_counts_that_differ_from_the_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_sittings(scratch_session)
    real_add_many = CRUDLeavePeriodPrinting.add_many

    def add_many_one_short(
        self: CRUDLeavePeriodPrinting,
        leave_period_printings: list[LeavePeriodPrinting],
    ) -> None:
        real_add_many(self, leave_period_printings[:-1])

    monkeypatch.setattr(CRUDLeavePeriodPrinting, "add_many", add_many_one_short)

    with pytest.raises(
        HansardWriteCheckError, match="Stored leave period printings by format"
    ):
        apply_leave_periods(is_commit=True)

    assert _get_stored_printings(scratch_session) == []


def _seed_sitting_with_attendance_offices(session: Session) -> None:
    lee = Speaker(
        name="Lee Hsien Loong",
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    tan = Speaker(
        name="Tan Wu Meng",
        party="PAP",
        is_legislative_assembly=False,
        parliament_number=_PARLIAMENT_NUMBER,
    )
    session.add_all([lee, tan])
    session.commit()
    sitting = _build_sitting(
        1,
        "6-3-2020",
        _build_permission_list(
            "Mr Lee Hsien Loong", "Dr Tan Wu Meng", "Mr Nobody Known"
        ),
    )
    sitting.attendance_list = json.dumps(
        [
            {
                "mpName": f"Mr Lee Hsien Loong (Ang Mo Kio), {_OFFICE_PRINTED}.",
                "attendance": True,
                "locationName": "Ang Mo Kio",
            },
            {
                "mpName": "Dr Tan Wu Meng (Jurong).",
                "attendance": True,
                "locationName": "Jurong",
            },
        ]
    )
    session.add(sitting)
    session.commit()
    session.add_all(
        [
            Attendance(
                sitting_id=1,
                speaker_name="Lee Hsien Loong",
                is_present=True,
                speaker_id=lee.id,
            ),
            Attendance(
                sitting_id=1,
                speaker_name="Tan Wu Meng",
                is_present=True,
                speaker_id=tan.id,
            ),
        ]
    )
    session.commit()


def test_a_linked_printing_takes_the_office_its_sitting_prints(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sitting_with_attendance_offices(scratch_session)

    apply_leave_periods(is_commit=True)

    printing = scratch_session.exec(
        select(LeavePeriodPrinting).where(LeavePeriodPrinting.ordinal == 1)
    ).one()
    assert printing.office_printed == _OFFICE_PRINTED
    assert printing.office_source == LeaveOfficeSource.ATTENDANCE_LIST


def test_a_linked_printing_with_no_printed_office_stays_none(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sitting_with_attendance_offices(scratch_session)

    apply_leave_periods(is_commit=True)

    printing = scratch_session.exec(
        select(LeavePeriodPrinting).where(
            LeavePeriodPrinting.ordinal == _UNOFFICED_ROW_ORDINAL
        )
    ).one()
    assert printing.speaker_id is not None
    assert printing.office_printed is None
    assert printing.office_source is None


def test_an_unlinked_printing_has_no_office(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_sitting_with_attendance_offices(scratch_session)

    apply_leave_periods(is_commit=True)

    printing = scratch_session.exec(
        select(LeavePeriodPrinting).where(
            LeavePeriodPrinting.ordinal == _UNLINKED_ROW_ORDINAL
        )
    ).one()
    assert printing.speaker_id is None
    assert printing.office_printed is None
    assert printing.office_source is None


_ENTRY_OFFICE_PRINTED = "Minister for Law"
_UNLINKED_ENTRY_OFFICE_PRINTED = "Minister for Culture"


def _build_older_entry(
    ordinal: int, printed_name: str, start_day: int, office_printed: Optional[str]
) -> LeaveEntry:
    return LeaveEntry(
        ordinal=ordinal,
        printed_name=printed_name,
        carried_name=None,
        printed_from=None,
        printed_to=None,
        printed_line=f"{printed_name} - line {ordinal}",
        printed_heading_from=None,
        printed_heading_to=None,
        office_printed=office_printed,
        leave_dates=LeaveDates(date(2020, 3, start_day), date(2020, 3, start_day + 1)),
        end_text=None,
        entry_format=LeaveEntryFormat.PROSE_RANGE,
        name_source=LeaveNameSource.PRINTED,
        year_source=LeaveYearSource.PRINTED_IN_ENTRY,
    )


def test_an_office_printed_on_the_entry_comes_before_the_attendance_entry(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_sitting_with_attendance_offices(scratch_session)
    older_entries = [
        _build_older_entry(1, "Mr Lee Hsien Loong", 5, _ENTRY_OFFICE_PRINTED),
        _build_older_entry(2, "Mr Lee Hsien Loong", 8, None),
        _build_older_entry(3, "Mr Nobody Known", 5, _UNLINKED_ENTRY_OFFICE_PRINTED),
    ]
    monkeypatch.setattr(
        "populate.leave_periods._get_leave_entries",
        lambda sitting_leave_text_row,
        sitting_date,
        leave_date_misprints: older_entries,
    )

    apply_leave_periods(is_commit=True)

    printings = scratch_session.exec(
        select(LeavePeriodPrinting).order_by(col(LeavePeriodPrinting.ordinal))
    ).all()
    assert [
        (printing.office_printed, printing.office_source) for printing in printings
    ] == [
        (_ENTRY_OFFICE_PRINTED, LeaveOfficeSource.PRINTED_ON_ENTRY),
        (_OFFICE_PRINTED, LeaveOfficeSource.ATTENDANCE_LIST),
        (_UNLINKED_ENTRY_OFFICE_PRINTED, LeaveOfficeSource.PRINTED_ON_ENTRY),
    ]


_OLDER_SITTING_ID = 2
_OLDER_UNREAD_LINE = "Mr Garbled - nothing to read here"
_OLDER_MARKDOWN = "\n".join(
    [
        "Permission to Members to be Absent",
        "Mr Lee Hsien Loong (Ang Mo Kio), Prime Minister - from 5th to 7th March, 1970.",
        _OLDER_UNREAD_LINE,
    ]
)


def _seed_markdown_and_list_sittings(session: Session) -> None:
    session.add_all(
        [
            _build_sitting(1, "6-3-2020", _build_permission_list("Mr Lee Hsien Loong")),
            Sitting(
                id=_OLDER_SITTING_ID,
                sitting_date="6-3-1970",
                parlement_no=_PARLIAMENT_NUMBER,
                markdown_content=_OLDER_MARKDOWN,
            ),
        ]
    )
    session.commit()


def test_a_markdown_sitting_and_a_list_sitting_are_planned_in_one_commit(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_markdown_and_list_sittings(scratch_session)

    apply_leave_periods(is_commit=True)

    printings = scratch_session.exec(select(LeavePeriodPrinting)).all()
    assert Counter(printing.entry_format for printing in printings) == {
        LeaveEntryFormat.STRUCTURED_LIST: 1,
        LeaveEntryFormat.PROSE_RANGE: 1,
        LeaveEntryFormat.UNREAD: 1,
    }
    range_printing = next(
        printing
        for printing in printings
        if printing.entry_format == LeaveEntryFormat.PROSE_RANGE
    )
    assert range_printing.sitting_id == _OLDER_SITTING_ID
    assert range_printing.office_printed == _OFFICE_PRINTED
    assert range_printing.office_source == LeaveOfficeSource.PRINTED_ON_ENTRY


def test_an_unread_line_is_stored_with_its_printed_line_and_no_dates(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_markdown_and_list_sittings(scratch_session)

    apply_leave_periods(is_commit=True)

    unread_printing = scratch_session.exec(
        select(LeavePeriodPrinting).where(
            LeavePeriodPrinting.entry_format == LeaveEntryFormat.UNREAD
        )
    ).one()
    unread_period = scratch_session.get(LeavePeriod, unread_printing.leave_period_id)
    assert unread_printing.printed_line == _OLDER_UNREAD_LINE
    assert unread_printing.printed_name is None
    assert unread_printing.name_source == LeaveNameSource.NONE
    assert unread_printing.year_source is None
    assert unread_printing.is_covering_sitting is None
    assert unread_period is not None
    assert unread_period.start_date is None
    assert unread_period.end_date is None
    assert unread_period.period_key == f"entry|{_OLDER_SITTING_ID}|2"
