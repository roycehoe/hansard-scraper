import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

import scripts.apply_divisions as apply_divisions_script
from database.division import Division
from database.division_vote import DivisionVote
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from database.report import Report
from database.speech import Speech
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    MinutesDivisionPairing,
    MinutesStatus,
    SpeechKind,
)
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from schemas.division_plan import DivisionPlan
from scripts.apply_divisions import apply_divisions
from tests.division_seed import add_division_report, add_division_speech_rows

_PROTECTED_DATABASE_URL = "postgresql://u:p@localhost:5432/x"
_SITTING_DATE = datetime(2018, 1, 10)
_LINE_FIRST = "The House divided: Ayes, 10; Noes, 3."
_LINE_SECOND = "The House divided: Ayes, 20; Noes, 4."
_TOTAL_ONLY = "There are 7 Ayes and 2 Noes."
_FIRST_REPORT_ID = "report-one"
_SECOND_REPORT_ID = "report-two"
_SEEDED_DIVISION_COUNT = 3
_DIVISION_TABLE_NAME = "division"


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


def _seed_reports(session: Session) -> tuple[Report, Report]:
    first = add_division_report(session, _FIRST_REPORT_ID, _SITTING_DATE)
    second = add_division_report(session, _SECOND_REPORT_ID, _SITTING_DATE)
    add_division_speech_rows(
        session,
        first,
        [
            (SpeechKind.PROCEDURAL, None, _LINE_FIRST),
            (SpeechKind.PROCEDURAL, None, _LINE_SECOND),
        ],
    )
    add_division_speech_rows(session, second, [(SpeechKind.SPEECH, None, _TOTAL_ONLY)])
    session.commit()
    return first, second


def _get_division_count(session: Session) -> int:
    session.expire_all()
    return session.exec(select(func.count()).select_from(Division)).one()


def _get_division_ids(session: Session) -> list[int]:
    session.expire_all()
    return [
        division_id
        for division_id in session.exec(select(Division.id).order_by(Division.id)).all()
        if division_id is not None
    ]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_divisions_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_divisions_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_the_plan_file_only(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"

    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)

    assert log_recorder.messages == [
        "Plan: 3 divisions in 2 reports, 0 unread rows",
        "Divisions by decade and source: 2010s PRINTED_LINE 2, 2010s SPOKEN_TOTAL 1",
        "Unread rows by reason: none",
        "Against stored: 0 kept, 0 updated, 3 added, 0 deleted",
        "Plan: 0 paired divisions at risk, 0 with the line gone",
        "Dry run: nothing written",
    ]
    plan = DivisionPlan.model_validate_json(plan_path.read_text())
    assert len(plan.divisions) == _SEEDED_DIVISION_COUNT
    assert _get_division_count(scratch_session) == 0


def test_commit_stores_the_plan_and_a_second_commit_writes_nothing(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        apply_divisions_script, "vacuum_analyze_written_tables", _VacuumRecorder()
    )
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)

    apply_divisions([], plan_path, is_commit=True, is_detach_paired=False)
    first_ids = _get_division_ids(scratch_session)
    apply_divisions([], plan_path, is_commit=True, is_detach_paired=False)

    assert len(first_ids) == _SEEDED_DIVISION_COUNT
    assert _get_division_ids(scratch_session) == first_ids
    assert log_recorder.messages[-3] == (
        "Against stored: 3 kept, 0 updated, 0 added, 0 deleted"
    )


def test_commit_refuses_a_plan_that_differs_from_the_reviewed_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    tmp_path: Path,
) -> None:
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)
    reviewed_plan = json.loads(plan_path.read_text())
    reviewed_plan["divisions"][0]["printed_counts"] = "Changed"
    plan_path.write_text(json.dumps(reviewed_plan))

    with pytest.raises(HansardWriteCheckError, match="differs from the reviewed plan"):
        apply_divisions([], plan_path, is_commit=True, is_detach_paired=False)

    assert _get_division_count(scratch_session) == 0


def test_commit_refuses_the_protected_port_before_any_row_is_read(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)
    monkeypatch.setattr(
        apply_divisions_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )
    monkeypatch.setattr(apply_divisions_script, "engine", None)

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_divisions([], plan_path, is_commit=True, is_detach_paired=False)

    assert _get_division_count(scratch_session) == 0


def test_report_id_limits_the_plan_to_the_given_reports(
    scratch_session: Session, log_recorder: _LogRecorder, tmp_path: Path
) -> None:
    first, _ = _seed_reports(scratch_session)
    assert first.id is not None
    plan_path = tmp_path / "plan.json"

    apply_divisions([first.id], plan_path, is_commit=False, is_detach_paired=False)

    plan = DivisionPlan.model_validate_json(plan_path.read_text())
    assert plan.sprs_report_ids == [_FIRST_REPORT_ID]
    assert {division.sprs_report_id for division in plan.divisions} == {
        _FIRST_REPORT_ID
    }


def test_commit_vacuums_the_division_table(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vacuum_recorder = _VacuumRecorder()
    monkeypatch.setattr(
        apply_divisions_script, "vacuum_analyze_written_tables", vacuum_recorder
    )
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)

    apply_divisions([], plan_path, is_commit=True, is_detach_paired=False)

    assert vacuum_recorder.table_names == [[_DIVISION_TABLE_NAME]]


_NOT_A_DIVISION_LINE = "The Bill was read a second time."
_MINUTES_PRINTED_COUNTS = "On Question put, a division was taken: Ayes 10, Noes 3."
_FIRST_AYES = 10
_FIRST_NOES = 3
_CHANGED_AYES = 99


def _store_and_pair_first_division(
    session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> int:
    monkeypatch.setattr(
        apply_divisions_script, "vacuum_analyze_written_tables", _VacuumRecorder()
    )
    _seed_reports(session)
    apply_divisions(
        [],
        tmp_path / "seed-plan.json",
        is_commit=False,
        is_detach_paired=False,
    )
    apply_divisions(
        [], tmp_path / "seed-plan.json", is_commit=True, is_detach_paired=False
    )
    division_id = session.exec(
        select(Division.id).where(
            Division.report_division_number == 1,
            Division.sprs_report_id == _FIRST_REPORT_ID,
        )
    ).one()
    assert division_id is not None
    minutes = Minutes(sitting_date=_SITTING_DATE.date(), status=MinutesStatus.TEXT_STORED)
    session.add(minutes)
    session.flush()
    assert minutes.id is not None
    session.add(
        MinutesDivision(
            ordinal=1,
            printed_counts=_MINUTES_PRINTED_COUNTS,
            ayes=_FIRST_AYES,
            noes=_FIRST_NOES,
            list_status=DivisionListStatus.NOT_PRINTED,
            pairing=MinutesDivisionPairing.PAIRED,
            minutes_id=minutes.id,
            division_id=division_id,
        )
    )
    session.add_all(
        DivisionVote(
            ordinal=1,
            printed_name="Mr A",
            vote_choice=DivisionVoteChoice.AYE,
            list_source=list_source,
            division_id=division_id,
        )
        for list_source in DivisionVoteListSource
    )
    session.commit()
    return division_id


def _remove_first_division_line(session: Session) -> None:
    speech = session.exec(
        select(Speech).where(Speech.transcript == _LINE_FIRST)
    ).one()
    speech.transcript = _NOT_A_DIVISION_LINE
    session.commit()


def _get_vote_sources(session: Session, division_id: int) -> list[DivisionVoteListSource]:
    session.expire_all()
    return sorted(
        session.exec(
            select(DivisionVote.list_source).where(
                DivisionVote.division_id == division_id
            )
        ).all()
    )


def test_a_paired_division_whose_line_has_gone_is_refused_before_any_write(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    division_id = _store_and_pair_first_division(
        scratch_session, log_recorder, monkeypatch, tmp_path
    )
    _remove_first_division_line(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)

    with pytest.raises(HansardWriteCheckError, match="--detach-paired"):
        apply_divisions([], plan_path, is_commit=True, is_detach_paired=False)

    scratch_session.rollback()
    assert _get_division_ids(scratch_session).count(division_id) == 1
    stored_division = scratch_session.get(Division, division_id)
    assert stored_division is not None
    assert stored_division.sprs_report_id == _FIRST_REPORT_ID
    assert _get_vote_sources(scratch_session, division_id) == sorted(
        DivisionVoteListSource
    )


def test_detach_paired_rewrites_the_division_to_the_minutes_counts(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    division_id = _store_and_pair_first_division(
        scratch_session, log_recorder, monkeypatch, tmp_path
    )
    _remove_first_division_line(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)

    apply_divisions([], plan_path, is_commit=True, is_detach_paired=True)

    scratch_session.expire_all()
    detached_division = scratch_session.get(Division, division_id)
    assert detached_division is not None
    assert detached_division.sprs_report_id is None
    assert detached_division.report_division_number is None
    assert detached_division.speech_ordinal is None
    assert detached_division.count_source == DivisionCountSource.MINUTES
    assert detached_division.printed_counts == _MINUTES_PRINTED_COUNTS
    assert (detached_division.ayes, detached_division.noes) == (
        _FIRST_AYES,
        _FIRST_NOES,
    )
    assert detached_division.list_status == DivisionListStatus.NOT_PRINTED
    assert _get_vote_sources(scratch_session, division_id) == [
        DivisionVoteListSource.MINUTES
    ]
    minutes_division = scratch_session.exec(select(MinutesDivision)).one()
    assert minutes_division.pairing == MinutesDivisionPairing.NO_MATCHING_DIVISION
    assert minutes_division.division_id == division_id


def test_a_paired_division_whose_counts_would_change_is_refused_even_with_detach_paired(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    division_id = _store_and_pair_first_division(
        scratch_session, log_recorder, monkeypatch, tmp_path
    )
    stored_division = scratch_session.get(Division, division_id)
    assert stored_division is not None
    stored_division.ayes = _CHANGED_AYES
    scratch_session.commit()
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)

    with pytest.raises(HansardWriteCheckError, match="change its Ayes or Noes"):
        apply_divisions([], plan_path, is_commit=True, is_detach_paired=True)

    scratch_session.rollback()
    scratch_session.expire_all()
    refused_division = scratch_session.get(Division, division_id)
    assert refused_division is not None
    assert refused_division.ayes == _CHANGED_AYES
    assert refused_division.sprs_report_id == _FIRST_REPORT_ID


def test_an_unpaired_division_whose_line_has_gone_is_deleted_without_the_option(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        apply_divisions_script, "vacuum_analyze_written_tables", _VacuumRecorder()
    )
    _seed_reports(scratch_session)
    plan_path = tmp_path / "plan.json"
    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)
    apply_divisions([], plan_path, is_commit=True, is_detach_paired=False)
    _remove_first_division_line(scratch_session)
    apply_divisions([], plan_path, is_commit=False, is_detach_paired=False)

    apply_divisions([], plan_path, is_commit=True, is_detach_paired=False)

    assert _get_division_count(scratch_session) == _SEEDED_DIVISION_COUNT - 1


def test_the_dry_run_logs_the_paired_divisions_at_risk(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    division_id = _store_and_pair_first_division(
        scratch_session, log_recorder, monkeypatch, tmp_path
    )
    _remove_first_division_line(scratch_session)
    log_recorder.messages.clear()

    apply_divisions(
        [], tmp_path / "plan.json", is_commit=False, is_detach_paired=False
    )

    assert (
        f"Paired division {division_id} of report {_FIRST_REPORT_ID} (The House divided: Ayes, 10; Noes, 3): line gone"
        in log_recorder.messages
    )
    assert (
        "Plan: 1 paired divisions at risk, 1 with the line gone"
        in log_recorder.messages
    )
