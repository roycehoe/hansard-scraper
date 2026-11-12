import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

import scripts.apply_division_party_counts as apply_division_party_counts_script
from crud.division_party_count import CRUDDivisionPartyCount
from database.division import Division
from database.division_party_count import DivisionPartyCount
from database.division_vote import DivisionVote
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    MinutesDivisionPairing,
    MinutesStatus,
)
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from populate.division_party_counts import populate_division_party_counts
from schemas.division_party_count_plan import DivisionPartyCountPlan
from scripts.apply_division_party_counts import apply_division_party_counts

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_SITTING_DATE = date(2021, 10, 4)
_PARLIAMENT_NUMBER = 14
_PRINTED_COUNTS = "Ayes 2, Noes 1"
_PARTY = "PAP"
_OTHER_PARTY = "WP"
_HANSARD_ROW_COUNT = 2
_MINUTES_ROW_COUNT = 1
_DELETE_PREFIX = "DELETE"


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


def _add_division_with_hansard_votes(session: Session) -> int:
    division = Division(
        sitting_date=_SITTING_DATE,
        parliament_number=_PARLIAMENT_NUMBER,
        count_source=DivisionCountSource.PRINTED_LINE,
        printed_counts=_PRINTED_COUNTS,
        ayes=2,
        noes=1,
        list_status=DivisionListStatus.STORED,
    )
    session.add(division)
    session.flush()
    assert division.id is not None
    session.add_all(
        DivisionVote(
            ordinal=ordinal,
            printed_name=f"Member {ordinal}",
            vote_choice=vote_choice,
            list_source=DivisionVoteListSource.HANSARD,
            party=party,
            division_id=division.id,
        )
        for ordinal, (vote_choice, party) in enumerate(
            (
                (DivisionVoteChoice.AYE, _PARTY),
                (DivisionVoteChoice.AYE, _PARTY),
                (DivisionVoteChoice.NO, _OTHER_PARTY),
            ),
            1,
        )
    )
    session.commit()
    return division.id


def _add_stored_minutes_list(session: Session, division_id: int) -> None:
    minutes = Minutes(sitting_date=_SITTING_DATE, status=MinutesStatus.TEXT_STORED)
    session.add(minutes)
    session.flush()
    assert minutes.id is not None
    session.add(
        MinutesDivision(
            ordinal=1,
            printed_counts=_PRINTED_COUNTS,
            ayes=2,
            noes=1,
            list_status=DivisionListStatus.STORED,
            pairing=MinutesDivisionPairing.PAIRED,
            minutes_id=minutes.id,
            division_id=division_id,
        )
    )
    session.add(
        DivisionVote(
            ordinal=1,
            printed_name="Member 1",
            vote_choice=DivisionVoteChoice.AYE,
            list_source=DivisionVoteListSource.MINUTES,
            party=_PARTY,
            division_id=division_id,
        )
    )
    session.commit()


def _get_party_counts(session: Session) -> list[DivisionPartyCount]:
    session.expire_all()
    return list(
        session.exec(
            select(DivisionPartyCount).order_by(
                DivisionPartyCount.list_source, DivisionPartyCount.id
            )
        ).all()
    )


def _get_party_count_count(session: Session) -> int:
    session.expire_all()
    return session.exec(select(func.count()).select_from(DivisionPartyCount)).one()


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_division_party_counts_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_division_party_counts_script, "logger", recorder)
    monkeypatch.setattr(
        apply_division_party_counts_script,
        "vacuum_analyze_written_tables",
        _VacuumRecorder(),
    )
    return recorder


def test_dry_run_writes_the_plan_and_no_rows(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    division_id = _add_division_with_hansard_votes(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_division_party_counts([], plan_path, is_commit=False)

    plan = DivisionPartyCountPlan.model_validate_json(plan_path.read_text())
    assert plan.division_ids == [division_id]
    assert len(plan.party_counts) == _HANSARD_ROW_COUNT
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_party_count_count(scratch_session) == 0


def test_commit_refuses_a_changed_plan(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    division_id = _add_division_with_hansard_votes(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_division_party_counts([], plan_path, is_commit=False)
    reviewed_plan = json.loads(plan_path.read_text())
    reviewed_plan["division_ids"] = [division_id + 1]
    plan_path.write_text(json.dumps(reviewed_plan))

    with pytest.raises(HansardWriteCheckError, match="differs from the reviewed plan"):
        apply_division_party_counts([], plan_path, is_commit=True)

    assert _get_party_count_count(scratch_session) == 0


def test_commit_to_a_protected_database_raises_write_target_error(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _add_division_with_hansard_votes(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_division_party_counts([], plan_path, is_commit=False)
    monkeypatch.setattr(
        apply_division_party_counts_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )
    monkeypatch.setattr(apply_division_party_counts_script, "engine", None)

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_division_party_counts([], plan_path, is_commit=True)

    assert _get_party_count_count(scratch_session) == 0


def test_commit_stores_the_breakdown_and_a_rerun_replaces_it(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    division_id = _add_division_with_hansard_votes(scratch_session)
    first_plan_path = tmp_path / "first.json"
    apply_division_party_counts([], first_plan_path, is_commit=False)
    apply_division_party_counts([], first_plan_path, is_commit=True)
    hansard_counts = [
        (party_count.list_source, party_count.party, party_count.member_count)
        for party_count in _get_party_counts(scratch_session)
    ]
    _add_stored_minutes_list(scratch_session, division_id)
    second_plan_path = tmp_path / "second.json"

    apply_division_party_counts([], second_plan_path, is_commit=False)
    apply_division_party_counts([], second_plan_path, is_commit=True)

    assert hansard_counts == [
        (DivisionVoteListSource.HANSARD, _PARTY, 2),
        (DivisionVoteListSource.HANSARD, _OTHER_PARTY, 1),
    ]
    minutes_counts = _get_party_counts(scratch_session)
    assert len(minutes_counts) == _MINUTES_ROW_COUNT
    assert minutes_counts[0].list_source == DivisionVoteListSource.MINUTES
    assert (minutes_counts[0].party, minutes_counts[0].member_count) == (_PARTY, 1)


def test_a_breakdown_delete_that_returns_a_wrong_count_refuses_the_rewrite(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _add_division_with_hansard_votes(scratch_session)
    first_plan_path = tmp_path / "first.json"
    apply_division_party_counts([], first_plan_path, is_commit=False)
    apply_division_party_counts([], first_plan_path, is_commit=True)
    second_plan_path = tmp_path / "second.json"
    apply_division_party_counts([], second_plan_path, is_commit=False)
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
        apply_division_party_counts([], second_plan_path, is_commit=True)

    assert _get_party_count_count(scratch_session) == _HANSARD_ROW_COUNT


def test_populate_division_party_counts_emits_no_delete(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    division_id = _add_division_with_hansard_votes(scratch_session)
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
        populate_division_party_counts(scratch_session, [division_id])
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert _get_party_count_count(scratch_session) == _HANSARD_ROW_COUNT
    assert not [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(_DELETE_PREFIX)
    ]


def test_populate_division_party_counts_skips_a_division_that_already_has_rows(
    scratch_session: Session,
) -> None:
    division_id = _add_division_with_hansard_votes(scratch_session)
    populate_division_party_counts(scratch_session, [division_id])
    scratch_session.commit()

    populate_division_party_counts(scratch_session, [division_id])
    scratch_session.commit()

    assert _get_party_count_count(scratch_session) == _HANSARD_ROW_COUNT
