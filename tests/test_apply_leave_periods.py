import json
from datetime import date
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, select

import scripts.apply_leave_periods as apply_leave_periods_script
from crud.leave_period_printing import CRUDLeavePeriodPrinting
from database.leave_period import LeavePeriod, LeavePeriodPrinting
from database.sitting import Sitting
from database.speaker import Speaker
from enums import LeaveNameSource, LeaveSpeakerLinkSource
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from populate.leave_periods import populate_leave_periods
from scripts.apply_leave_periods import apply_leave_periods

_PARLIAMENT_NUMBER = 14
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"
_NAMED_KEY = "mr lee hsien loong|2020-03-05|2020-03-07"
_UNMERGED_KEY = "entry|3|1"
_PLAN_LOG = "Plan: 4 printings in 2 periods"
_BLANK_ROW_ORDINAL = 2


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
