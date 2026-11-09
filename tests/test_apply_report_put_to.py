from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, select

import scripts.apply_report_put_to as apply_report_put_to_script
from crud.report_put_to import CRUDReportPutTo
from database.report import Report
from database.report_put_to import ReportPutTo
from database.speech import Speech
from enums import ReportPutToSource, ReportType, ReportVersion, SpeechKind
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from populate.report_put_to import populate_report_put_to
from scripts.apply_report_put_to import apply_report_put_to

_PARLIAMENT_NUMBER = 14
_RECENT_SITTING_DATE = datetime(2025, 4, 2)
_OLDER_SITTING_DATE = datetime(1996, 3, 5)
_HEALTH_TRANSCRIPT = "asked the Minister for Health if clinics will open."
_DEFENCE_TRANSCRIPT = "To ask the Minister for Defence for details of the review."
_REPEATED_HEALTH_TRANSCRIPT = "asked the Minister for Health about waiting times."
_PRIME_MINISTER_TRANSCRIPT = "asked the Prime Minister whether the review is done."
_ANSWER_TRANSCRIPT = "The answer is in the annex."
_HAND_EDITED_OFFICE = "Hand edited"
_PLAN_LOG = (
    "Plan: 3 report put-tos for 3 reports;"
    " by decade: 1990 1, 2020 2;"
    " by source: ASKED_THE 2, TO_ASK_THE 1;"
    " 1 reports with no phrase"
)
_EMPTY_PLAN_LOG = (
    "Plan: 0 report put-tos for 0 reports;"
    " by decade: none; by source: none; 0 reports with no phrase"
)
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"


@dataclass(frozen=True)
class _SeededReports:
    oral_report: Report
    older_written_report: Report
    annex_report: Report
    motion_report: Report


class _LogRecorder:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _build_report(
    report_id: str, report_type: ReportType, sitting_date: datetime
) -> Report:
    return Report(
        volumeNo=_PARLIAMENT_NUMBER,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=sitting_date,
        sno=1,
        original_title=report_id,
        title=report_id,
        reportId=report_id,
        reportType=report_type,
        content=None,
        markdown_content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _build_speech(report: Report, ordinal: int, transcript: str) -> Speech:
    assert report.id is not None
    return Speech(
        ordinal=ordinal,
        speaker=None,
        transcript=transcript,
        kind=SpeechKind.SPEECH,
        speaker_id=None,
        sitting_date=report.sitting_date,
        report_type=report.report_type,
        report_id=report.id,
    )


def _seed_reports(session: Session) -> _SeededReports:
    oral_report = _build_report("oral", ReportType.ORAL_ANSWER, _RECENT_SITTING_DATE)
    older_written_report = _build_report(
        "older-written", ReportType.WRITTEN_ANSWER, _OLDER_SITTING_DATE
    )
    annex_report = _build_report(
        "annex", ReportType.WRITTEN_ANSWER_NOT_AVAILABLE, _RECENT_SITTING_DATE
    )
    motion_report = _build_report("motion", ReportType.MOTION, _RECENT_SITTING_DATE)
    session.add_all([oral_report, older_written_report, annex_report, motion_report])
    session.flush()
    session.add_all(
        [
            _build_speech(oral_report, 1, _HEALTH_TRANSCRIPT),
            _build_speech(oral_report, 2, _DEFENCE_TRANSCRIPT),
            _build_speech(oral_report, 3, _REPEATED_HEALTH_TRANSCRIPT),
            _build_speech(older_written_report, 1, _PRIME_MINISTER_TRANSCRIPT),
            _build_speech(annex_report, 1, _ANSWER_TRANSCRIPT),
            _build_speech(motion_report, 1, _HEALTH_TRANSCRIPT),
        ]
    )
    session.commit()
    return _SeededReports(
        oral_report, older_written_report, annex_report, motion_report
    )


def _get_oral_rows() -> list[tuple]:
    return [
        (
            "oral",
            1,
            "Minister for Health",
            "asked the Minister for Health",
            ReportPutToSource.ASKED_THE,
            1,
        ),
        (
            "oral",
            2,
            "Minister for Defence",
            "ask the Minister for Defence",
            ReportPutToSource.TO_ASK_THE,
            2,
        ),
    ]


def _get_older_written_rows() -> list[tuple]:
    return [
        (
            "older-written",
            1,
            "Prime Minister",
            "asked the Prime Minister",
            ReportPutToSource.ASKED_THE,
            1,
        )
    ]


def _get_stored_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return [
        (
            report_put_to.sprs_report_id,
            report_put_to.ordinal,
            report_put_to.office_printed,
            report_put_to.printed_text,
            report_put_to.source,
            report_put_to.first_ordinal,
        )
        for report_put_to in session.exec(
            select(ReportPutTo).order_by(
                ReportPutTo.sprs_report_id, ReportPutTo.ordinal
            )
        ).all()
    ]


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_report_put_to_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_report_put_to_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_reports(scratch_session)

    apply_report_put_to([], is_commit=False)

    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_stored_rows(scratch_session) == []


def test_commit_writes_the_planned_rows_of_the_question_reports_only(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_reports(scratch_session)

    apply_report_put_to([], is_commit=True)

    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Committed"
    assert _get_stored_rows(scratch_session) == (
        _get_older_written_rows() + _get_oral_rows()
    )


def test_commit_on_a_rerun_leaves_the_same_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_reports(scratch_session)
    apply_report_put_to([], is_commit=True)

    apply_report_put_to([], is_commit=True)

    assert log_recorder.messages.count(_PLAN_LOG) > 1
    assert _get_stored_rows(scratch_session) == (
        _get_older_written_rows() + _get_oral_rows()
    )


def test_commit_with_report_ids_leaves_other_reports_rows_alone(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    apply_report_put_to([], is_commit=True)
    older_written_put_to = scratch_session.exec(
        select(ReportPutTo).where(ReportPutTo.sprs_report_id == "older-written")
    ).one()
    older_written_put_to.office_printed = _HAND_EDITED_OFFICE
    scratch_session.commit()

    apply_report_put_to([seeded_reports.oral_report.id], is_commit=True)

    hand_edited_row = (
        "older-written",
        1,
        _HAND_EDITED_OFFICE,
        "asked the Prime Minister",
        ReportPutToSource.ASKED_THE,
        1,
    )
    assert _get_stored_rows(scratch_session) == [hand_edited_row] + _get_oral_rows()


def test_commit_of_a_report_that_is_not_a_question_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)

    apply_report_put_to([seeded_reports.motion_report.id], is_commit=True)

    assert _EMPTY_PLAN_LOG in log_recorder.messages
    assert _get_stored_rows(scratch_session) == []


def test_populate_inserts_the_rows_of_new_reports_and_issues_no_delete(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    assert seeded_reports.oral_report.id is not None
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
        populate_report_put_to(scratch_session, [seeded_reports.oral_report.id])
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert any(
        statement.startswith("INSERT INTO report_put_to") for statement in statements
    )
    assert not [statement for statement in statements if statement.startswith("DELETE")]
    assert _get_stored_rows(scratch_session) == _get_oral_rows()


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)
    monkeypatch.setattr(
        apply_report_put_to_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_report_put_to([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []


def test_commit_refuses_a_short_delete_count_and_keeps_the_rows(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)
    apply_report_put_to([], is_commit=True)
    real_delete_by_sprs_report_ids = CRUDReportPutTo.delete_by_sprs_report_ids

    def delete_by_sprs_report_ids_one_short(
        self: CRUDReportPutTo, sprs_report_ids: list[str]
    ) -> int:
        return real_delete_by_sprs_report_ids(self, sprs_report_ids) - 1

    monkeypatch.setattr(
        CRUDReportPutTo,
        "delete_by_sprs_report_ids",
        delete_by_sprs_report_ids_one_short,
    )

    with pytest.raises(
        HansardWriteCheckError, match="Deleted 2 report put-tos, read 3"
    ):
        apply_report_put_to([], is_commit=True)

    assert _get_stored_rows(scratch_session) == (
        _get_older_written_rows() + _get_oral_rows()
    )


def test_commit_refuses_stored_rows_that_differ_from_the_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)
    real_add_many = CRUDReportPutTo.add_many

    def add_many_without_the_last_row(
        self: CRUDReportPutTo, report_put_tos: list[ReportPutTo]
    ) -> None:
        real_add_many(self, report_put_tos[:-1])

    monkeypatch.setattr(CRUDReportPutTo, "add_many", add_many_without_the_last_row)

    with pytest.raises(HansardWriteCheckError, match="Stored report put-tos by decade"):
        apply_report_put_to([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []
