from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, select

import scripts.apply_report_askers as apply_report_askers_script
from crud.report_asker import CRUDReportAsker
from database.report import Report
from database.report_asker import ReportAsker
from database.speaker import Speaker
from database.speech import Speech
from enums import ReportAskerSource, ReportType, ReportVersion, SpeechKind
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from populate.report_askers import populate_report_askers
from scripts.apply_report_askers import apply_report_askers

_PARLIAMENT_NUMBER = 14
_SITTING_DATE = datetime(2025, 4, 2)
_STOOD_LINE = "The following Question stood in the name of Mr Louis Chua –"
_COUNTS_LOG = (
    "2 reports, 2 with an asker;"
    " 4 rows: ASKED_LINE 1, NAME_IN_TEXT 1, STOOD_IN_NAME_LINE 1, TO_ASK_LINE 1;"
    " 1 with no speaker_id; stood: 1 with a reader, 0 without"
)
_PLAN_LOG = "Plan: 4 report askers for 2 reports"
_EMPTY_PLAN_LOG = "Plan: 0 report askers for 0 reports"
_HAND_EDITED_NAME = "Hand edited"
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"


@dataclass(frozen=True)
class _SeededReports:
    chua: Speaker
    giam: Speaker
    singh: Speaker
    oral_report: Report
    written_report: Report
    motion_report: Report


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


def _build_report(report_id: str, report_type: ReportType) -> Report:
    return Report(
        volumeNo=_PARLIAMENT_NUMBER,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=_SITTING_DATE,
        sno=1,
        original_title="Sample Question",
        title="Sample Question",
        reportId=report_id,
        reportType=report_type,
        content=None,
        htmlFileName=None,
        reportVersion=ReportVersion.SPRS3,
    )


def _build_speech(
    report: Report,
    ordinal: int,
    speaker: Optional[str],
    speaker_id: Optional[int],
    kind: SpeechKind,
    transcript: str,
) -> Speech:
    assert report.id is not None
    return Speech(
        ordinal=ordinal,
        speaker=speaker,
        transcript=transcript,
        kind=kind,
        speaker_id=speaker_id,
        sitting_date=_SITTING_DATE,
        report_type=report.report_type,
        report_id=report.id,
    )


def _seed_reports(session: Session) -> _SeededReports:
    chua = _build_speaker("Louis Chua")
    giam = _build_speaker("Gerald Giam")
    singh = _build_speaker("Pritam Singh")
    oral_report = _build_report("oral", ReportType.ORAL_ANSWER)
    written_report = _build_report("written", ReportType.WRITTEN_ANSWER)
    motion_report = _build_report("motion", ReportType.MOTION)
    session.add_all([chua, giam, singh, oral_report, written_report, motion_report])
    session.flush()
    session.add_all(
        [
            _build_speech(
                oral_report, 1, None, None, SpeechKind.PROCEDURAL, _STOOD_LINE
            ),
            _build_speech(
                oral_report,
                2,
                "Mr Louis Chua",
                chua.id,
                SpeechKind.SPEECH,
                "1 To ask the Minister for Health whether the wait for a polyclinic appointment has changed.",
            ),
            _build_speech(
                oral_report,
                3,
                "Mr Gerald Giam",
                giam.id,
                SpeechKind.SPEECH,
                "Sir, Question No 1.",
            ),
            _build_speech(
                oral_report,
                4,
                "Mr Pritam Singh",
                singh.id,
                SpeechKind.SPEECH,
                "asked the Minister for Health how many polyclinic places were added.",
            ),
            _build_speech(
                oral_report,
                5,
                None,
                None,
                SpeechKind.UNCLASSIFIED,
                "Mr Nobody Known asked the Minister for Health how many clinics opened.",
            ),
            _build_speech(
                written_report,
                1,
                "Mr Gerald Giam",
                giam.id,
                SpeechKind.SPEECH,
                "To ask the Minister for Health how many clinics opened.",
            ),
            _build_speech(
                motion_report,
                1,
                "Mr Pritam Singh",
                singh.id,
                SpeechKind.SPEECH,
                "asked the Minister for Health about the motion.",
            ),
        ]
    )
    session.commit()
    return _SeededReports(chua, giam, singh, oral_report, written_report, motion_report)


def _get_oral_rows(seeded_reports: _SeededReports) -> list[tuple]:
    return [
        (
            seeded_reports.oral_report.id,
            1,
            "Mr Louis Chua",
            ReportAskerSource.STOOD_IN_NAME_LINE,
            "Mr Gerald Giam",
            seeded_reports.chua.id,
            seeded_reports.giam.id,
        ),
        (
            seeded_reports.oral_report.id,
            2,
            "Mr Pritam Singh",
            ReportAskerSource.ASKED_LINE,
            None,
            seeded_reports.singh.id,
            None,
        ),
        (
            seeded_reports.oral_report.id,
            3,
            "Mr Nobody Known",
            ReportAskerSource.NAME_IN_TEXT,
            None,
            None,
            None,
        ),
    ]


def _get_written_rows(seeded_reports: _SeededReports) -> list[tuple]:
    return [
        (
            seeded_reports.written_report.id,
            1,
            "Mr Gerald Giam",
            ReportAskerSource.TO_ASK_LINE,
            None,
            seeded_reports.giam.id,
            None,
        )
    ]


def _get_stored_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return sorted(
        (
            report_asker.report_id,
            report_asker.ordinal,
            report_asker.printed_name,
            report_asker.source,
            report_asker.reader_printed_name,
            report_asker.speaker_id,
            report_asker.reader_speaker_id,
        )
        for report_asker in session.exec(select(ReportAsker)).all()
    )


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_report_askers_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_report_askers_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_reports(scratch_session)

    apply_report_askers([], is_commit=False)

    assert f"Parliament 14: {_COUNTS_LOG}" in log_recorder.messages
    assert f"All: {_COUNTS_LOG}" in log_recorder.messages
    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_stored_rows(scratch_session) == []


def test_commit_writes_the_planned_rows_of_the_question_reports_only(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)

    apply_report_askers([], is_commit=True)

    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Committed"
    assert _get_stored_rows(scratch_session) == (
        _get_oral_rows(seeded_reports) + _get_written_rows(seeded_reports)
    )


def test_commit_on_a_rerun_leaves_the_same_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    apply_report_askers([], is_commit=True)

    apply_report_askers([], is_commit=True)

    assert log_recorder.messages.count(_PLAN_LOG) > 1
    assert _get_stored_rows(scratch_session) == (
        _get_oral_rows(seeded_reports) + _get_written_rows(seeded_reports)
    )


def test_commit_with_report_ids_leaves_other_reports_rows_alone(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    apply_report_askers([], is_commit=True)
    written_report_asker = next(
        report_asker
        for report_asker in scratch_session.exec(select(ReportAsker)).all()
        if report_asker.report_id == seeded_reports.written_report.id
    )
    written_report_asker.printed_name = _HAND_EDITED_NAME
    scratch_session.commit()

    apply_report_askers([seeded_reports.oral_report.id], is_commit=True)

    assert _get_stored_rows(scratch_session) == (
        _get_oral_rows(seeded_reports)
        + [
            (
                seeded_reports.written_report.id,
                1,
                _HAND_EDITED_NAME,
                ReportAskerSource.TO_ASK_LINE,
                None,
                seeded_reports.giam.id,
                None,
            )
        ]
    )


def test_commit_of_a_report_that_is_not_a_question_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)

    apply_report_askers([seeded_reports.motion_report.id], is_commit=True)

    assert _EMPTY_PLAN_LOG in log_recorder.messages
    assert _get_stored_rows(scratch_session) == []


def test_populate_inserts_the_rows_of_new_reports_and_issues_no_delete(
    scratch_engine: Engine, scratch_session: Session
) -> None:
    seeded_reports = _seed_reports(scratch_session)
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
        populate_report_askers(
            scratch_session,
            [
                seeded_reports.oral_report.id,
                seeded_reports.written_report.id,
                seeded_reports.motion_report.id,
            ],
        )
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert any(
        statement.startswith("INSERT INTO report_asker") for statement in statements
    )
    assert not [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("DELETE")
    ]
    assert _get_stored_rows(scratch_session) == (
        _get_oral_rows(seeded_reports) + _get_written_rows(seeded_reports)
    )


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)
    monkeypatch.setattr(
        apply_report_askers_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_report_askers([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []


def test_commit_refuses_a_short_delete_count_and_keeps_the_rows(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    apply_report_askers([], is_commit=True)
    real_delete_by_report_ids = CRUDReportAsker.delete_by_report_ids

    def delete_by_report_ids_one_short(
        self: CRUDReportAsker, report_ids: list[int]
    ) -> int:
        return real_delete_by_report_ids(self, report_ids) - 1

    monkeypatch.setattr(
        CRUDReportAsker, "delete_by_report_ids", delete_by_report_ids_one_short
    )

    with pytest.raises(HansardWriteCheckError, match="Deleted 3 report askers, read 4"):
        apply_report_askers([], is_commit=True)

    assert _get_stored_rows(scratch_session) == (
        _get_oral_rows(seeded_reports) + _get_written_rows(seeded_reports)
    )


def test_commit_refuses_stored_rows_that_differ_from_the_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)
    real_add_many = CRUDReportAsker.add_many

    def add_many_one_short(
        self: CRUDReportAsker, report_askers: list[ReportAsker]
    ) -> None:
        real_add_many(self, report_askers[:-1])

    monkeypatch.setattr(CRUDReportAsker, "add_many", add_many_one_short)

    with pytest.raises(
        HansardWriteCheckError, match="Parliament 14: stored report askers by source"
    ):
        apply_report_askers([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []
