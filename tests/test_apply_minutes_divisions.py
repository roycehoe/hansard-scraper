import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

import scripts.apply_minutes_divisions as apply_minutes_divisions_script
from crud.division_party_count import CRUDDivisionPartyCount
from database.division import Division
from database.division_party_count import DivisionPartyCount
from database.division_vote import DivisionVote
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from database.report import Report
from database.speaker import Speaker
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    DivisionVoteNameRule,
    MinutesDivisionPairing,
    MinutesStatus,
)
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from populate.minutes_divisions import (
    TWO_PARLIAMENTS_STATUS_NOTE,
    UNREAD_DIVISION_STATUS_NOTE,
    get_minutes_division_plan,
    populate_minutes_divisions,
)
from schemas.minutes_division_plan import MinutesDivisionPlan
from scripts.apply_minutes_divisions import apply_minutes_divisions
from tests.division_seed import add_division_report

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures"
_SITTING_DATE = date(2021, 10, 4)
_NEXT_SITTING_DATE = date(2021, 10, 5)
_PARLIAMENT_NUMBER = 14
_OTHER_PARLIAMENT_NUMBER = 15
_REPORT_ID = "minutes-report"
_VOTE_ROW_COUNT = 88
_AYE_COUNT = 75
_NO_COUNT = 11
_ABSTAIN_COUNT = 2
_DIVISION_COUNT = 2
_LINKED_NAME_COUNT = 4
_DATE_MISMATCH_NOTE = "the file date disagrees with the sitting"
_UNREAD_TEXT = "On Question put, the House divided."
_PRINTED_COUNTS = "Ayes 75, Noes 11, Abstentions 2"
_LINKED_SPEAKER_NAMES = (
    "Lee Hsien Loong",
    "Pritam Singh",
    "Shahira Abdullah",
    "Louis Chua Kheng Wee",
)
_VOTE_INSERT_PREFIX = "INSERT INTO division_vote"
_HAND_LIST_PRINTED_NAME = "Masagos Zulkifli B M M"
_HAND_LIST_CANONICAL_NAME = "Masagos Zulkifli Bin Masagos Mohamad"
_HAND_LIST_MINUTES_TEXT = """
On Question put, a division was taken: Ayes 2, Noes 1.

Ayes                          Noes

Masagos Zulkifli B M M        Pritam Singh
Lee Hsien Loong
"""


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


class _VacuumRecorder:
    def __init__(self) -> None:
        self.table_names: list[list[str]] = []

    def __call__(self, session: Session, table_names: list[str]) -> None:
        self.table_names.append(table_names)


def _read_fixture(name: str) -> str:
    return (_FIXTURE_DIRECTORY / name).read_text(encoding="utf-8")


def _add_speakers(session: Session) -> None:
    session.add_all(
        Speaker(
            name=name,
            party="PAP",
            is_legislative_assembly=False,
            parliament_number=_PARLIAMENT_NUMBER,
        )
        for name in _LINKED_SPEAKER_NAMES
    )
    session.flush()


def _add_minutes(
    session: Session,
    sitting_date: date,
    extracted_text: Optional[str],
    status: MinutesStatus = MinutesStatus.TEXT_STORED,
    status_note: Optional[str] = None,
) -> int:
    minutes = Minutes(
        sitting_date=sitting_date,
        status=status,
        status_note=status_note,
        extracted_text=extracted_text,
    )
    session.add(minutes)
    session.flush()
    assert minutes.id is not None
    return minutes.id


def _add_hansard_divisions(
    session: Session, report: Report, abstentions: int, count: int = _DIVISION_COUNT
) -> list[int]:
    divisions = [
        Division(
            sitting_date=report.sitting_date.date(),
            parliament_number=report.parliament_number,
            report_division_number=number,
            speech_ordinal=number,
            count_source=DivisionCountSource.PRINTED_LINE,
            printed_counts=_PRINTED_COUNTS,
            ayes=_AYE_COUNT,
            noes=_NO_COUNT,
            abstentions=abstentions,
            list_status=DivisionListStatus.NOT_PRINTED,
            sprs_report_id=report.report_id,
        )
        for number in range(1, count + 1)
    ]
    session.add_all(divisions)
    session.flush()
    return [division.id for division in divisions if division.id is not None]


def _seed_standard(session: Session) -> tuple[Report, int]:
    _add_speakers(session)
    report = add_division_report(
        session,
        _REPORT_ID,
        datetime(2021, 10, 4),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    minutes_id = _add_minutes(
        session, _SITTING_DATE, _read_fixture("minutes_2021_10_04.txt")
    )
    session.commit()
    return report, minutes_id


def _get_count(session: Session, table: type) -> int:
    session.expire_all()
    return session.exec(select(func.count()).select_from(table)).one()


def _get_minutes_divisions(session: Session) -> list[MinutesDivision]:
    session.expire_all()
    return list(
        session.exec(
            select(MinutesDivision).order_by(
                MinutesDivision.minutes_id, MinutesDivision.ordinal
            )
        ).all()
    )


def _get_minutes(session: Session, minutes_id: int) -> Minutes:
    session.expire_all()
    minutes = session.get(Minutes, minutes_id)
    assert minutes is not None
    return minutes


def _get_stored_state(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (
            minutes_division.minutes_id,
            minutes_division.ordinal,
            minutes_division.pairing,
            minutes_division.list_status,
            len(
                session.exec(
                    select(DivisionVote).where(
                        DivisionVote.division_id == minutes_division.division_id
                    )
                ).all()
            ),
        )
        for minutes_division in _get_minutes_divisions(session)
    ]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_minutes_divisions_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_minutes_divisions_script, "logger", recorder)
    monkeypatch.setattr(
        apply_minutes_divisions_script,
        "vacuum_analyze_written_tables",
        _VacuumRecorder(),
    )
    return recorder


def _commit(plan_path: Path, minutes_ids: list[int]) -> None:
    apply_minutes_divisions(minutes_ids, plan_path, is_commit=False)
    apply_minutes_divisions(minutes_ids, plan_path, is_commit=True)


def test_dry_run_writes_the_plan_and_no_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _, minutes_id = _seed_standard(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_minutes_divisions([minutes_id], plan_path, is_commit=False)

    plan = MinutesDivisionPlan.model_validate_json(plan_path.read_text())
    assert plan.minutes_ids == [minutes_id]
    assert len(plan.minutes_divisions) == _DIVISION_COUNT
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_count(scratch_session, MinutesDivision) == 0
    assert _get_count(scratch_session, DivisionVote) == 0
    assert _get_count(scratch_session, Division) == 0


def test_commit_refuses_a_changed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _, minutes_id = _seed_standard(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_minutes_divisions([minutes_id], plan_path, is_commit=False)
    reviewed_plan = json.loads(plan_path.read_text())
    reviewed_plan["minutes_ids"] = [minutes_id + 1]
    plan_path.write_text(json.dumps(reviewed_plan))

    with pytest.raises(HansardWriteCheckError, match="differs from the reviewed plan"):
        apply_minutes_divisions([minutes_id], plan_path, is_commit=True)

    assert _get_count(scratch_session, MinutesDivision) == 0


def test_commit_to_a_protected_database_raises_write_target_error(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, minutes_id = _seed_standard(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_minutes_divisions([minutes_id], plan_path, is_commit=False)
    monkeypatch.setattr(
        apply_minutes_divisions_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )
    monkeypatch.setattr(apply_minutes_divisions_script, "engine", None)

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_minutes_divisions([minutes_id], plan_path, is_commit=True)

    assert _get_count(scratch_session, MinutesDivision) == 0


def test_commit_stores_two_divisions_and_their_vote_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _, minutes_id = _seed_standard(scratch_session)

    _commit(tmp_path / "plan.json", [minutes_id])

    minutes_divisions = _get_minutes_divisions(scratch_session)
    assert len(minutes_divisions) == _DIVISION_COUNT
    for minutes_division in minutes_divisions:
        vote_rows = scratch_session.exec(
            select(DivisionVote).where(
                DivisionVote.division_id == minutes_division.division_id
            )
        ).all()
        assert len(vote_rows) == _VOTE_ROW_COUNT
        assert {vote_row.list_source for vote_row in vote_rows} == {
            DivisionVoteListSource.MINUTES
        }
        assert (
            sum(vote_row.speaker_id is not None for vote_row in vote_rows)
            == _LINKED_NAME_COUNT
        )
        assert Counter(vote_row.vote_choice for vote_row in vote_rows) == {
            DivisionVoteChoice.AYE: _AYE_COUNT,
            DivisionVoteChoice.NO: _NO_COUNT,
            DivisionVoteChoice.ABSTAIN: _ABSTAIN_COUNT,
        }
        assert all(
            vote_row.party == "PAP"
            for vote_row in vote_rows
            if vote_row.speaker_id is not None
        )
        assert all(
            vote_row.party is None and vote_row.name_rule is None
            for vote_row in vote_rows
            if vote_row.speaker_id is None
        )


def test_a_second_commit_with_the_same_plan_writes_the_same_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _, minutes_id = _seed_standard(scratch_session)
    plan_path = tmp_path / "plan.json"
    _commit(plan_path, [minutes_id])
    first_state = _get_stored_state(scratch_session)

    apply_minutes_divisions([minutes_id], plan_path, is_commit=True)

    assert _get_stored_state(scratch_session) == first_state
    assert _get_count(scratch_session, DivisionVote) == _VOTE_ROW_COUNT * 2
    assert _get_count(scratch_session, Division) == _DIVISION_COUNT


def test_a_division_with_no_hansard_division_creates_a_minutes_only_division(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _, minutes_id = _seed_standard(scratch_session)

    _commit(tmp_path / "plan.json", [minutes_id])

    minutes_divisions = _get_minutes_divisions(scratch_session)
    assert {
        minutes_division.pairing for minutes_division in minutes_divisions
    } == {MinutesDivisionPairing.NO_MATCHING_DIVISION}
    divisions = scratch_session.exec(select(Division)).all()
    assert len(divisions) == _DIVISION_COUNT
    for division in divisions:
        assert division.count_source == DivisionCountSource.MINUTES
        assert division.sprs_report_id is None
        assert division.parliament_number == _PARLIAMENT_NUMBER
        assert division.sitting_date == _SITTING_DATE
        assert division.list_status == DivisionListStatus.NOT_PRINTED
    assert {division.id for division in divisions} == {
        minutes_division.division_id for minutes_division in minutes_divisions
    }


def test_a_division_with_differing_abstentions_creates_its_own_new_division(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    report, minutes_id = _seed_standard(scratch_session)
    hansard_division_ids = _add_hansard_divisions(
        scratch_session, report, abstentions=_ABSTAIN_COUNT + 1
    )
    scratch_session.commit()

    _commit(tmp_path / "plan.json", [minutes_id])

    minutes_divisions = _get_minutes_divisions(scratch_session)
    assert {
        minutes_division.pairing for minutes_division in minutes_divisions
    } == {MinutesDivisionPairing.ABSTENTIONS_DIFFER}
    assert not {
        minutes_division.division_id for minutes_division in minutes_divisions
    } & set(hansard_division_ids)
    divisions = scratch_session.exec(select(Division)).all()
    assert len(divisions) == _DIVISION_COUNT + len(hansard_division_ids)
    minutes_only_divisions = [
        division
        for division in divisions
        if division.count_source == DivisionCountSource.MINUTES
    ]
    assert len(minutes_only_divisions) == _DIVISION_COUNT
    assert all(division.sprs_report_id is None for division in minutes_only_divisions)


def test_a_paired_division_attaches_the_minutes_vote_rows_to_the_hansard_division(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    report, minutes_id = _seed_standard(scratch_session)
    hansard_division_ids = _add_hansard_divisions(
        scratch_session, report, abstentions=_ABSTAIN_COUNT
    )
    scratch_session.commit()

    _commit(tmp_path / "plan.json", [minutes_id])

    minutes_divisions = _get_minutes_divisions(scratch_session)
    assert [
        minutes_division.pairing for minutes_division in minutes_divisions
    ] == [MinutesDivisionPairing.PAIRED] * _DIVISION_COUNT
    assert [
        minutes_division.division_id for minutes_division in minutes_divisions
    ] == hansard_division_ids
    assert _get_count(scratch_session, Division) == len(hansard_division_ids)
    assert _get_count(scratch_session, DivisionVote) == _VOTE_ROW_COUNT * _DIVISION_COUNT


def test_a_counts_disagree_division_stores_no_vote_rows_but_keeps_the_printed_list(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_speakers(scratch_session)
    add_division_report(
        scratch_session,
        _REPORT_ID,
        datetime(2021, 10, 4),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    minutes_id = _add_minutes(
        scratch_session,
        _SITTING_DATE,
        _read_fixture("minutes_2021_10_04_name_moved.txt"),
    )
    scratch_session.commit()

    _commit(tmp_path / "plan.json", [minutes_id])

    first, second = _get_minutes_divisions(scratch_session)
    assert first.list_status == DivisionListStatus.COUNTS_DISAGREE
    assert first.printed_list is not None
    assert (
        scratch_session.exec(
            select(func.count())
            .select_from(DivisionVote)
            .where(DivisionVote.division_id == first.division_id)
        ).one()
        == 0
    )
    assert second.list_status == DivisionListStatus.STORED
    assert (
        scratch_session.exec(
            select(func.count())
            .select_from(DivisionVote)
            .where(DivisionVote.division_id == second.division_id)
        ).one()
        == _VOTE_ROW_COUNT
    )


def test_an_unread_division_mention_moves_the_file_to_needs_review_and_writes_no_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    add_division_report(
        scratch_session,
        _REPORT_ID,
        datetime(2021, 10, 4),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    minutes_id = _add_minutes(scratch_session, _SITTING_DATE, _UNREAD_TEXT)
    scratch_session.commit()

    _commit(tmp_path / "plan.json", [minutes_id])

    minutes = _get_minutes(scratch_session, minutes_id)
    assert minutes.status == MinutesStatus.NEEDS_REVIEW
    assert minutes.status_note == UNREAD_DIVISION_STATUS_NOTE
    assert _get_count(scratch_session, MinutesDivision) == 0
    assert _get_count(scratch_session, DivisionVote) == 0
    assert _get_count(scratch_session, Division) == 0


def test_a_needs_review_file_with_a_date_mismatch_note_plans_no_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_speakers(scratch_session)
    add_division_report(
        scratch_session,
        _REPORT_ID,
        datetime(2021, 10, 4),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    minutes_id = _add_minutes(
        scratch_session,
        _SITTING_DATE,
        _read_fixture("minutes_2021_10_04.txt"),
        MinutesStatus.NEEDS_REVIEW,
        _DATE_MISMATCH_NOTE,
    )
    scratch_session.commit()

    plan = get_minutes_division_plan(scratch_session, [minutes_id])
    _commit(tmp_path / "plan.json", [minutes_id])
    review_note = populate_minutes_divisions(scratch_session, minutes_id)
    scratch_session.commit()

    assert plan.minutes_ids == []
    assert plan.minutes_divisions == []
    assert review_note is None
    assert _get_count(scratch_session, MinutesDivision) == 0
    assert _get_count(scratch_session, DivisionVote) == 0
    minutes = _get_minutes(scratch_session, minutes_id)
    assert minutes.status == MinutesStatus.NEEDS_REVIEW
    assert minutes.status_note == _DATE_MISMATCH_NOTE


def test_a_flagged_file_that_is_needs_review_with_another_note_does_not_raise(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    add_division_report(
        scratch_session,
        _REPORT_ID,
        datetime(2021, 10, 4),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    add_division_report(
        scratch_session,
        "next-report",
        datetime(2021, 10, 5),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    other_note_id = _add_minutes(
        scratch_session,
        _SITTING_DATE,
        _UNREAD_TEXT,
        MinutesStatus.NEEDS_REVIEW,
        _DATE_MISMATCH_NOTE,
    )
    own_note_id = _add_minutes(
        scratch_session,
        _NEXT_SITTING_DATE,
        _UNREAD_TEXT,
        MinutesStatus.NEEDS_REVIEW,
        UNREAD_DIVISION_STATUS_NOTE,
    )
    scratch_session.commit()

    _commit(tmp_path / "plan.json", [other_note_id, own_note_id])

    other_note_minutes = _get_minutes(scratch_session, other_note_id)
    assert other_note_minutes.status_note == _DATE_MISMATCH_NOTE
    own_note_minutes = _get_minutes(scratch_session, own_note_id)
    assert own_note_minutes.status == MinutesStatus.NEEDS_REVIEW
    assert own_note_minutes.status_note == UNREAD_DIVISION_STATUS_NOTE


def test_a_date_with_two_parliament_numbers_flags_only_that_file(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _add_speakers(scratch_session)
    add_division_report(
        scratch_session,
        _REPORT_ID,
        datetime(2021, 10, 4),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    add_division_report(
        scratch_session,
        "other-parliament-report",
        datetime(2021, 10, 4),
        parliament_number=_OTHER_PARLIAMENT_NUMBER,
    )
    add_division_report(
        scratch_session,
        "next-report",
        datetime(2021, 10, 5),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    flagged_id = _add_minutes(
        scratch_session, _SITTING_DATE, _read_fixture("minutes_2021_10_04.txt")
    )
    written_id = _add_minutes(
        scratch_session, _NEXT_SITTING_DATE, _read_fixture("minutes_2021_10_04.txt")
    )
    scratch_session.commit()

    _commit(tmp_path / "plan.json", [flagged_id, written_id])

    flagged_minutes = _get_minutes(scratch_session, flagged_id)
    assert flagged_minutes.status == MinutesStatus.NEEDS_REVIEW
    assert flagged_minutes.status_note == TWO_PARLIAMENTS_STATUS_NOTE
    written_minutes = _get_minutes(scratch_session, written_id)
    assert written_minutes.status == MinutesStatus.TEXT_STORED
    assert {
        minutes_division.minutes_id
        for minutes_division in _get_minutes_divisions(scratch_session)
    } == {written_id}


def test_an_explicit_minutes_id_before_the_first_date_is_skipped(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    add_division_report(
        scratch_session,
        _REPORT_ID,
        datetime(2008, 9, 30),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    minutes_id = _add_minutes(
        scratch_session, date(2008, 9, 30), _read_fixture("minutes_2021_10_04.txt")
    )
    scratch_session.commit()

    plan = get_minutes_division_plan(scratch_session, [minutes_id])
    _commit(tmp_path / "plan.json", [minutes_id])

    assert plan.minutes_ids == []
    assert _get_count(scratch_session, MinutesDivision) == 0
    assert _get_count(scratch_session, Division) == 0


def test_a_rerun_over_a_date_with_a_minutes_only_division_gives_the_same_plan_and_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _, minutes_id = _seed_standard(scratch_session)
    scratch_session.add(
        Division(
            sitting_date=_SITTING_DATE,
            parliament_number=_PARLIAMENT_NUMBER,
            count_source=DivisionCountSource.MINUTES,
            printed_counts=_PRINTED_COUNTS,
            ayes=_AYE_COUNT,
            noes=_NO_COUNT,
            abstentions=_ABSTAIN_COUNT,
            list_status=DivisionListStatus.NOT_PRINTED,
            sprs_report_id=None,
        )
    )
    scratch_session.commit()
    first_plan_path = tmp_path / "first.json"
    _commit(first_plan_path, [minutes_id])
    first_state = _get_stored_state(scratch_session)
    first_division_count = _get_count(scratch_session, Division)
    second_plan_path = tmp_path / "second.json"

    apply_minutes_divisions([minutes_id], second_plan_path, is_commit=False)
    apply_minutes_divisions([minutes_id], second_plan_path, is_commit=True)

    assert MinutesDivisionPlan.model_validate_json(
        second_plan_path.read_text()
    ) == MinutesDivisionPlan.model_validate_json(first_plan_path.read_text())
    assert {
        minutes_division.pairing
        for minutes_division in _get_minutes_divisions(scratch_session)
    } == {MinutesDivisionPairing.NO_MATCHING_DIVISION}
    assert _get_stored_state(scratch_session) == first_state
    assert _get_count(scratch_session, Division) == first_division_count


def test_a_hand_listed_name_that_two_speaker_rows_hold_links_to_nobody(
    scratch_session: Session,
) -> None:
    scratch_session.add(
        Speaker(
            name=_HAND_LIST_CANONICAL_NAME,
            party="PAP",
            is_legislative_assembly=False,
            parliament_number=_PARLIAMENT_NUMBER,
        )
    )
    add_division_report(
        scratch_session,
        _REPORT_ID,
        datetime(2021, 10, 4),
        parliament_number=_PARLIAMENT_NUMBER,
    )
    minutes_id = _add_minutes(scratch_session, _SITTING_DATE, _HAND_LIST_MINUTES_TEXT)
    scratch_session.commit()

    one_row_plan = get_minutes_division_plan(scratch_session, [minutes_id])
    scratch_session.add(
        Speaker(
            name=_HAND_LIST_CANONICAL_NAME,
            party="PAP",
            is_legislative_assembly=False,
            parliament_number=_PARLIAMENT_NUMBER,
        )
    )
    scratch_session.commit()
    two_row_plan = get_minutes_division_plan(scratch_session, [minutes_id])

    (one_row_vote,) = [
        vote
        for vote in one_row_plan.minutes_divisions[0].votes
        if vote.printed_name == _HAND_LIST_PRINTED_NAME
    ]
    (two_row_vote,) = [
        vote
        for vote in two_row_plan.minutes_divisions[0].votes
        if vote.printed_name == _HAND_LIST_PRINTED_NAME
    ]
    assert one_row_vote.name_rule == DivisionVoteNameRule.HAND_LIST
    assert one_row_vote.speaker_id is not None
    assert two_row_vote.speaker_id is None
    assert two_row_vote.name_rule is None


def test_populate_minutes_divisions_inserts_with_no_delete(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    _, minutes_id = _seed_standard(scratch_session)
    statements: list[str] = []

    def record_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        is_many: bool,
    ) -> None:
        statements.append(statement)

    event.listen(scratch_engine, "before_cursor_execute", record_statement)
    try:
        review_note = populate_minutes_divisions(scratch_session, minutes_id)
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert review_note is None
    assert any(
        statement.startswith(_VOTE_INSERT_PREFIX)
        for statement in statements
    )
    assert not [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("DELETE")
    ]
    assert len(_get_minutes_divisions(scratch_session)) == _DIVISION_COUNT


def test_a_breakdown_delete_that_returns_a_wrong_count_refuses_the_minutes_write(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, minutes_id = _seed_standard(scratch_session)
    first_plan_path = tmp_path / "first.json"
    _commit(first_plan_path, [minutes_id])
    scratch_session.add_all(
        DivisionPartyCount(
            member_count=_AYE_COUNT,
            uncertain_member_count=0,
            party="PAP",
            list_source=DivisionVoteListSource.MINUTES,
            vote_choice=DivisionVoteChoice.AYE,
            division_id=division.id,
        )
        for division in scratch_session.exec(select(Division)).all()
    )
    scratch_session.commit()
    party_count_total = _get_count(scratch_session, DivisionPartyCount)
    second_plan_path = tmp_path / "second.json"
    apply_minutes_divisions([minutes_id], second_plan_path, is_commit=False)
    delete_by_division_ids = CRUDDivisionPartyCount.delete_by_division_ids
    monkeypatch.setattr(
        CRUDDivisionPartyCount,
        "delete_by_division_ids",
        lambda crud_party_count, deleted_division_ids: delete_by_division_ids(
            crud_party_count, deleted_division_ids
        )
        - 1,
    )

    with pytest.raises(HansardWriteCheckError, match="party count rows"):
        apply_minutes_divisions([minutes_id], second_plan_path, is_commit=True)

    assert _get_count(scratch_session, DivisionPartyCount) == party_count_total


def test_a_rerun_after_a_breakdown_exists_deletes_the_breakdown_before_the_minutes_only_division(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _, minutes_id = _seed_standard(scratch_session)
    first_plan_path = tmp_path / "first.json"
    _commit(first_plan_path, [minutes_id])
    scratch_session.add_all(
        DivisionPartyCount(
            member_count=_AYE_COUNT,
            uncertain_member_count=0,
            party="PAP",
            list_source=DivisionVoteListSource.MINUTES,
            vote_choice=DivisionVoteChoice.AYE,
            division_id=division.id,
        )
        for division in scratch_session.exec(select(Division)).all()
    )
    scratch_session.commit()
    second_plan_path = tmp_path / "second.json"

    apply_minutes_divisions([minutes_id], second_plan_path, is_commit=False)
    apply_minutes_divisions([minutes_id], second_plan_path, is_commit=True)

    assert _get_count(scratch_session, Division) == _DIVISION_COUNT
    assert _get_count(scratch_session, DivisionPartyCount) == 0
