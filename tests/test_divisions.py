from datetime import datetime
from typing import Optional

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, col, delete, func, select

from crud.division import CRUDDivision
from database.division import Division
from database.division_party_count import DivisionPartyCount
from database.speech import Speech
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    SpeechKind,
)
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
_SITTING_DATE_1984 = datetime(1984, 7, 25)
_SINGULAR_AYE_LINE = "The House divided: Aye, 1; Noes, 54; Abstention, 1."
_FIFTY_AYES_LINE = "The House divided: Ayes, 50; No, 1; Abstention, 1."
_TAKE_A_DIVISION = "All right. Take a division."
_PARTY_MEMBER_COUNT = 40


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
        (
            division.sprs_report_id,
            division.report_division_number,
            division.count_source,
        )
        for division in plan.divisions
    ] == [
        (_FIRST_REPORT_ID, 1, DivisionCountSource.PRINTED_LINE),
        (_SECOND_REPORT_ID, 1, DivisionCountSource.SPOKEN_TOTAL),
    ]
    assert [division.list_status for division in plan.divisions] == [
        DivisionListStatus.LAYOUT_UNREADABLE,
        DivisionListStatus.NOT_PRINTED,
    ]


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
    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )

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
    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )
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

    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )

    stored = {
        division.printed_counts: division
        for division in _get_stored_divisions(scratch_session)
    }
    assert len(stored) == _STORED_DIVISION_COUNT
    kept = stored[_LINE_FIRST.removesuffix(".")]
    assert kept.id == old_id
    assert (kept.report_division_number, kept.speech_ordinal) == (2, 3)
    assert stored[_LINE_SECOND.removesuffix(".")].id != old_id


def test_a_division_read_before_a_stored_one_leaves_its_id_and_party_counts(
    scratch_session: Session,
) -> None:
    report = add_division_report(
        scratch_session, _FIRST_REPORT_ID, _SITTING_DATE_1984, parliament_number=6
    )
    add_division_speech_rows(
        scratch_session, report, [(SpeechKind.PROCEDURAL, None, _FIFTY_AYES_LINE)]
    )
    assert report.id is not None
    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )
    old_division = _get_stored_divisions(scratch_session)[0]
    assert old_division.id is not None
    party_count = DivisionPartyCount(
        member_count=_PARTY_MEMBER_COUNT,
        uncertain_member_count=0,
        party="People's Action Party",
        list_source=DivisionVoteListSource.HANSARD,
        vote_choice=DivisionVoteChoice.AYE,
        division_id=old_division.id,
    )
    scratch_session.add(party_count)
    scratch_session.flush()
    old_party_count_id = party_count.id
    for old_speech in scratch_session.exec(
        select(Speech).where(col(Speech.report_id) == report.id)
    ).all():
        scratch_session.delete(old_speech)
    scratch_session.flush()
    add_division_speech_rows(
        scratch_session,
        report,
        [
            (SpeechKind.SPEECH, "Mr Deputy Speaker", _TAKE_A_DIVISION),
            (SpeechKind.PROCEDURAL, None, _SINGULAR_AYE_LINE),
            (SpeechKind.SPEECH, None, _FILLER),
            (SpeechKind.PROCEDURAL, None, _FIFTY_AYES_LINE),
        ],
    )

    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )

    stored = {
        division.printed_counts: division
        for division in _get_stored_divisions(scratch_session)
    }
    kept = stored[_FIFTY_AYES_LINE.removesuffix(".")]
    assert kept.id == old_division.id
    assert (kept.report_division_number, kept.speech_ordinal) == (2, 4)
    added = stored[_SINGULAR_AYE_LINE.removesuffix(".")]
    assert added.id != old_division.id
    assert (added.report_division_number, added.speech_ordinal) == (1, 2)
    stored_party_counts = list(scratch_session.exec(select(DivisionPartyCount)).all())
    assert [
        (stored_party_count.id, stored_party_count.division_id)
        for stored_party_count in stored_party_counts
    ] == [(old_party_count_id, old_division.id)]


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
    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )
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

    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )

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
    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )
    stored_id = _get_stored_divisions(scratch_session)[0].id
    scratch_session.exec(delete(Speech).where(col(Speech.report_id) == report.id))
    plan = get_division_plan(scratch_session, [report.id])

    assert get_division_match(scratch_session, plan).division_ids_to_delete == [
        stored_id
    ]
    write_division_plan(scratch_session, plan)

    assert _get_stored_divisions(scratch_session) == []


def test_write_deletes_only_the_divisions_of_the_planned_reports(
    scratch_session: Session,
) -> None:
    first = add_division_report(scratch_session, _FIRST_REPORT_ID, _SITTING_DATE)
    second = add_division_report(scratch_session, _SECOND_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        scratch_session, first, [(SpeechKind.PROCEDURAL, None, _LINE_FIRST)]
    )
    add_division_speech_rows(
        scratch_session, second, [(SpeechKind.PROCEDURAL, None, _LINE_SECOND)]
    )
    assert first.id is not None and second.id is not None
    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [first.id, second.id])
    )
    second_division_id = next(
        division.id
        for division in _get_stored_divisions(scratch_session)
        if division.sprs_report_id == _SECOND_REPORT_ID
    )
    scratch_session.exec(delete(Speech).where(col(Speech.report_id) == first.id))
    plan = get_division_plan(scratch_session, [first.id])

    write_division_plan(scratch_session, plan)

    assert [
        (division.id, division.sprs_report_id)
        for division in _get_stored_divisions(scratch_session)
    ] == [(second_division_id, _SECOND_REPORT_ID)]


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
    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )
    scratch_session.exec(delete(Speech).where(col(Speech.report_id) == report.id))
    add_division_speech_rows(
        scratch_session,
        report,
        [
            (SpeechKind.PROCEDURAL, None, _LINE_SECOND),
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
        ],
    )

    write_division_plan(
        scratch_session, get_division_plan(scratch_session, [report.id])
    )
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
        if statement.lstrip()
        .upper()
        .startswith(("UPDATE DIVISION", "DELETE FROM DIVISION"))
    ]
    assert scratch_session.exec(select(func.count()).select_from(Division)).one() == 1
