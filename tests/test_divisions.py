from datetime import datetime
from typing import Optional

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, col, delete, func, select

from crud.division import CRUDDivision
from database.division import Division
from database.speech import Speech
from enums import DivisionCountSource, DivisionListStatus, SpeechKind
from exceptions import HansardWriteCheckError
from populate.divisions import (
    get_division_match,
    get_division_plan,
    populate_divisions,
    write_division_plan,
)
from tests.division_seed import add_division_report, add_division_speech_rows

_SITTING_DATE = datetime(2018, 1, 10)
_LINE_FIRST = "The House divided: Ayes, 10; Noes, 3."
_LINE_SECOND = "The House divided: Ayes, 20; Noes, 4."
_TOTAL_ONLY = "There are 7 Ayes and 2 Noes."
_UNREAD_OPENING = "The House divided and the Clerk proceeded to call out the names."
_FILLER = "Order, order."
_FIRST_REPORT_ID = "report-one"
_SECOND_REPORT_ID = "report-two"
_STORED_DIVISION_COUNT = 2


def _get_stored_divisions(session: Session) -> list[Division]:
    return list(
        session.exec(
            select(Division).order_by(
                col(Division.sprs_report_id), col(Division.report_division_number)
            )
        ).all()
    )


def _get_stored_numbers_and_counts(
    session: Session,
) -> list[tuple[Optional[int], str]]:
    return [
        (division.report_division_number, division.printed_counts)
        for division in _get_stored_divisions(session)
    ]


def test_plan_reads_the_divisions_of_each_report(scratch_session: Session) -> None:
    first = add_division_report(scratch_session, _FIRST_REPORT_ID, _SITTING_DATE)
    second = add_division_report(scratch_session, _SECOND_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        scratch_session, first, [(SpeechKind.PROCEDURAL, None, _LINE_FIRST)]
    )
    add_division_speech_rows(
        scratch_session, second, [(SpeechKind.SPEECH, None, _TOTAL_ONLY)]
    )
    assert first.id is not None and second.id is not None

    plan = get_division_plan(scratch_session, [second.id, first.id])

    assert plan.report_ids == [first.id, second.id]
    assert plan.sprs_report_ids == [_FIRST_REPORT_ID, _SECOND_REPORT_ID]
    assert [
        (division.sprs_report_id, division.report_division_number, division.count_source)
        for division in plan.divisions
    ] == [
        (_FIRST_REPORT_ID, 1, DivisionCountSource.PRINTED_LINE),
        (_SECOND_REPORT_ID, 1, DivisionCountSource.SPOKEN_TOTAL),
    ]
    assert {division.list_status for division in plan.divisions} == {
        DivisionListStatus.NOT_PRINTED
    }


def test_write_stores_the_plan_and_a_second_write_changes_nothing(
    scratch_session: Session,
) -> None:
    report = add_division_report(scratch_session, _FIRST_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        scratch_session,
        report,
        [
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
            (SpeechKind.SPEECH, None, _FILLER),
            (SpeechKind.PROCEDURAL, None, _LINE_SECOND),
        ],
    )
    assert report.id is not None
    plan = get_division_plan(scratch_session, [report.id])

    write_division_plan(scratch_session, plan)
    first_ids = [division.id for division in _get_stored_divisions(scratch_session)]
    write_division_plan(scratch_session, get_division_plan(scratch_session, [report.id]))

    assert len(first_ids) == _STORED_DIVISION_COUNT
    assert [
        division.id for division in _get_stored_divisions(scratch_session)
    ] == first_ids
    match = get_division_match(scratch_session, plan)
    assert match.division_updates == []
    assert match.divisions_to_add == []
    assert match.division_ids_to_delete == []


def test_write_keeps_the_id_of_a_matched_division_when_its_number_and_ordinal_move(
    scratch_session: Session,
) -> None:
    report = add_division_report(scratch_session, _FIRST_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        scratch_session, report, [(SpeechKind.PROCEDURAL, None, _LINE_FIRST)]
    )
    assert report.id is not None
    write_division_plan(scratch_session, get_division_plan(scratch_session, [report.id]))
    old_division = _get_stored_divisions(scratch_session)[0]
    old_id = old_division.id
    scratch_session.exec(delete(Speech).where(col(Speech.report_id) == report.id))
    add_division_speech_rows(
        scratch_session,
        report,
        [
            (SpeechKind.SPEECH, None, _FILLER),
            (SpeechKind.PROCEDURAL, None, _LINE_SECOND),
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
        ],
    )

    write_division_plan(scratch_session, get_division_plan(scratch_session, [report.id]))

    stored = {
        division.printed_counts: division
        for division in _get_stored_divisions(scratch_session)
    }
    assert len(stored) == _STORED_DIVISION_COUNT
    kept = stored[_LINE_FIRST.removesuffix(".")]
    assert kept.id == old_id
    assert (kept.report_division_number, kept.speech_ordinal) == (2, 3)
    assert stored[_LINE_SECOND.removesuffix(".")].id != old_id


def test_write_matches_equal_printed_counts_in_order(
    scratch_session: Session,
) -> None:
    report = add_division_report(scratch_session, _FIRST_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        scratch_session,
        report,
        [
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
        ],
    )
    assert report.id is not None
    write_division_plan(scratch_session, get_division_plan(scratch_session, [report.id]))
    first_ids = [division.id for division in _get_stored_divisions(scratch_session)]
    scratch_session.exec(delete(Speech).where(col(Speech.report_id) == report.id))
    add_division_speech_rows(
        scratch_session,
        report,
        [
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
            (SpeechKind.SPEECH, None, _FILLER),
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
        ],
    )

    write_division_plan(scratch_session, get_division_plan(scratch_session, [report.id]))

    stored = _get_stored_divisions(scratch_session)
    assert [division.id for division in stored] == first_ids
    assert [division.speech_ordinal for division in stored] == [1, 3]


def test_write_removes_a_division_the_plan_no_longer_holds(
    scratch_session: Session,
) -> None:
    report = add_division_report(scratch_session, _FIRST_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        scratch_session, report, [(SpeechKind.PROCEDURAL, None, _LINE_FIRST)]
    )
    assert report.id is not None
    write_division_plan(scratch_session, get_division_plan(scratch_session, [report.id]))
    stored_id = _get_stored_divisions(scratch_session)[0].id
    scratch_session.exec(delete(Speech).where(col(Speech.report_id) == report.id))
    plan = get_division_plan(scratch_session, [report.id])

    assert get_division_match(scratch_session, plan).division_ids_to_delete == [
        stored_id
    ]
    write_division_plan(scratch_session, plan)

    assert _get_stored_divisions(scratch_session) == []


def test_write_can_swap_two_division_numbers_in_one_write(
    scratch_session: Session,
) -> None:
    report = add_division_report(scratch_session, _FIRST_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        scratch_session,
        report,
        [
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
            (SpeechKind.PROCEDURAL, None, _LINE_SECOND),
        ],
    )
    assert report.id is not None
    write_division_plan(scratch_session, get_division_plan(scratch_session, [report.id]))
    scratch_session.exec(delete(Speech).where(col(Speech.report_id) == report.id))
    add_division_speech_rows(
        scratch_session,
        report,
        [
            (SpeechKind.PROCEDURAL, None, _LINE_SECOND),
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
        ],
    )

    write_division_plan(scratch_session, get_division_plan(scratch_session, [report.id]))
    scratch_session.commit()

    assert _get_stored_numbers_and_counts(scratch_session) == [
        (1, _LINE_SECOND.removesuffix(".")),
        (2, _LINE_FIRST.removesuffix(".")),
    ]


def test_write_refuses_a_commit_check_that_disagrees_with_the_plan(
    scratch_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = add_division_report(scratch_session, _FIRST_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        scratch_session,
        report,
        [
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
            (SpeechKind.PROCEDURAL, None, _LINE_SECOND),
        ],
    )
    assert report.id is not None
    plan = get_division_plan(scratch_session, [report.id])

    def add_all_but_one(self: CRUDDivision, divisions: list[Division]) -> None:
        self.session.add_all(divisions[1:])
        self.session.flush()

    monkeypatch.setattr(CRUDDivision, "add_many", add_all_but_one)

    with pytest.raises(HansardWriteCheckError):
        write_division_plan(scratch_session, plan)


def test_populate_divisions_inserts_only_and_returns_report_ids_with_unread_openings(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    good = add_division_report(scratch_session, _FIRST_REPORT_ID, _SITTING_DATE)
    unread = add_division_report(scratch_session, _SECOND_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        scratch_session, good, [(SpeechKind.PROCEDURAL, None, _LINE_FIRST)]
    )
    add_division_speech_rows(
        scratch_session, unread, [(SpeechKind.PROCEDURAL, None, _UNREAD_OPENING)]
    )
    assert good.id is not None and unread.id is not None
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
        report_ids = populate_divisions(scratch_session, [good.id, unread.id])
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert report_ids == [unread.id]
    assert not [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(("UPDATE DIVISION", "DELETE FROM DIVISION"))
    ]
    assert scratch_session.exec(select(func.count()).select_from(Division)).one() == 1
