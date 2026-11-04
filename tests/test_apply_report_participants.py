import json
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace
from typing import Optional

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Connection, Engine
from sqlmodel import Session, select

import scripts.apply_report_participants as apply_report_participants_script
from crud.report_asker import CRUDReportAsker
from crud.report_participant import CRUDReportParticipant
from crud.report_question_state import CRUDReportQuestionState
from database.attendance import Attendance
from database.report import Report
from database.report_asker import ReportAsker
from database.report_participant import ReportParticipant
from database.report_question_state import ReportQuestionState
from database.sitting import Sitting
from database.speaker import Speaker
from database.speech import Speech
from enums import (
    OfficeSource,
    ParticipantRole,
    ParticipantRoleSource,
    QuestionState,
    ReportType,
    ReportVersion,
    SpeechKind,
)
from exceptions import HansardWriteCheckError, HansardWriteTargetError
from populate.report_askers import populate_report_askers
from populate.report_participants import (
    get_report_participant_plan,
    populate_report_participants,
)
from scripts.apply_report_participants import apply_report_participants

_PARLIAMENT_NUMBER = 14
_FIRST_SITTING_DATE = datetime(2025, 4, 2)
_SECOND_SITTING_DATE = datetime(2025, 4, 3)
_THIRD_SITTING_DATE = datetime(2025, 4, 4)
_STOOD_LINE = "The following Question stood in the name of Mr Louis Chua –"
_MINISTER_OF_HEALTH_LABEL = "The Minister for Health (Mr Ong Ye Kung)"
_MINISTER_OF_HEALTH = "The Minister for Health"
_MINISTER_OF_MANPOWER = "Minister for Manpower"
_SENIOR_MINISTER_OF_STATE = "Senior Minister of State for Finance"
_HEADER_LINE = f"MPs Speaking: Dr Tan See Leng ({_MINISTER_OF_MANPOWER}), Mr Speaker"
_COUNTS_LOG = (
    "4 reports; 12 rows: ABSENT_FILER 1, ANSWERER 6, ASKER 4, READER 1;"
    " role source: ASKER_RULES 6, OFFICE_LABEL 1, OFFICE_ON_THE_DAY 5;"
    " office source: ATTENDANCE_LIST 2, HEADER_IN_REPORT 1, LABEL_IN_REPORT 1,"
    " LABEL_SAME_DAY 1, PARLIAMENT_GUESS 1;"
    " 1 with no speaker_id; states: NOT_A_QUESTION 1"
)
_PLAN_LOG = "Plan: 12 report participants and 1 report question states for 4 reports"
_EMPTY_PLAN_LOG = (
    "Plan: 0 report participants and 0 report question states for 0 reports"
)
_HAND_EDITED_NAME = "Hand edited"
_PROTECTED_DATABASE_URL = "postgresql://user:password@localhost:5432/hansard"


@dataclass(frozen=True)
class _SeededReports:
    chua: Speaker
    giam: Speaker
    singh: Speaker
    ong: Speaker
    tan: Speaker
    chee: Speaker
    oral_report: Report
    written_report: Report
    later_written_report: Report
    annex_report: Report
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


def _build_report(
    report_id: str,
    report_type: ReportType,
    sitting_date: datetime,
    title: str,
    markdown_content: Optional[str],
) -> Report:
    return Report(
        volumeNo=_PARLIAMENT_NUMBER,
        parlNo=_PARLIAMENT_NUMBER,
        sittingNo=None,
        sittingDate=sitting_date,
        sno=1,
        original_title=title,
        title=title,
        reportId=report_id,
        reportType=report_type,
        content=None,
        markdown_content=markdown_content,
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
        sitting_date=report.sitting_date,
        report_type=report.report_type,
        report_id=report.id,
    )


def _seed_reports(session: Session) -> _SeededReports:
    chua = _build_speaker("Louis Chua")
    giam = _build_speaker("Gerald Giam")
    singh = _build_speaker("Pritam Singh")
    ong = _build_speaker("Ong Ye Kung")
    tan = _build_speaker("Tan See Leng")
    chee = _build_speaker("Chee Hong Tat")
    oral_report = _build_report(
        "oral",
        ReportType.ORAL_ANSWER,
        _FIRST_SITTING_DATE,
        "Polyclinic Waiting Times",
        f"{_HEADER_LINE}\nThe questions follow.",
    )
    written_report = _build_report(
        "written",
        ReportType.WRITTEN_ANSWER,
        _FIRST_SITTING_DATE,
        "Clinics Opened",
        None,
    )
    later_written_report = _build_report(
        "later-written",
        ReportType.WRITTEN_ANSWER,
        _SECOND_SITTING_DATE,
        "Clinics To Open",
        None,
    )
    annex_report = _build_report(
        "annex",
        ReportType.WRITTEN_ANSWER_NOT_AVAILABLE,
        _SECOND_SITTING_DATE,
        "Annex A",
        None,
    )
    motion_report = _build_report(
        "motion", ReportType.MOTION, _FIRST_SITTING_DATE, "Motion", None
    )
    first_sitting = Sitting(
        sitting_date="2-4-2025",
        parlement_no=_PARLIAMENT_NUMBER,
        markdown_content=(
            f"PRESENT:\nMr Chee Hong Tat (Bishan-Toa Payoh), {_SENIOR_MINISTER_OF_STATE}.\n"
            "Mr Pritam Singh (Aljunied).\n"
        ),
    )
    second_sitting = Sitting(
        sitting_date="3-4-2025",
        parlement_no=_PARLIAMENT_NUMBER,
        attendance_list=json.dumps(
            [
                {
                    "mpName": f"Mr Chee Hong Tat (Bishan-Toa Payoh), {_SENIOR_MINISTER_OF_STATE}. ",
                    "attendance": True,
                    "locationName": "Bishan-Toa Payoh",
                }
            ]
        ),
    )
    session.add_all(
        [
            chua,
            giam,
            singh,
            ong,
            tan,
            chee,
            oral_report,
            written_report,
            later_written_report,
            annex_report,
            motion_report,
            first_sitting,
            second_sitting,
        ]
    )
    session.flush()
    session.add_all(
        [
            Attendance(
                sitting_id=sitting_id,
                speaker_name="Chee Hong Tat",
                is_present=True,
                speaker_id=chee.id,
            )
            for sitting_id in (first_sitting.id, second_sitting.id)
            if sitting_id is not None
        ]
    )
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
                oral_report,
                6,
                _MINISTER_OF_HEALTH_LABEL,
                ong.id,
                SpeechKind.SPEECH,
                "The wait has not changed.",
            ),
            _build_speech(
                oral_report,
                7,
                "Dr Tan See Leng",
                tan.id,
                SpeechKind.SPEECH,
                "Clinics employ more staff this year.",
            ),
            _build_speech(
                oral_report,
                8,
                "Mr Chee Hong Tat",
                chee.id,
                SpeechKind.SPEECH,
                "The new clinics opened in March.",
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
                written_report,
                2,
                "Mr Ong Ye Kung",
                ong.id,
                SpeechKind.SPEECH,
                "Fifteen clinics opened last year.",
            ),
            _build_speech(
                later_written_report,
                1,
                "Mr Pritam Singh",
                singh.id,
                SpeechKind.SPEECH,
                "To ask the Minister for Health how many clinics will open.",
            ),
            _build_speech(
                later_written_report,
                2,
                "Mr Ong Ye Kung",
                ong.id,
                SpeechKind.SPEECH,
                "Seven clinics will open.",
            ),
            _build_speech(
                later_written_report,
                3,
                "Mr Chee Hong Tat",
                chee.id,
                SpeechKind.SPEECH,
                "Two more will follow.",
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
    populate_report_askers(
        session,
        [
            report.id
            for report in (
                oral_report,
                written_report,
                later_written_report,
                annex_report,
                motion_report,
            )
            if report.id is not None
        ],
    )
    session.commit()
    return _SeededReports(
        chua,
        giam,
        singh,
        ong,
        tan,
        chee,
        oral_report,
        written_report,
        later_written_report,
        annex_report,
        motion_report,
    )


def _get_oral_rows(seeded_reports: _SeededReports) -> list[tuple]:
    report_id = seeded_reports.oral_report.id
    return [
        (
            report_id,
            1,
            ParticipantRole.ABSENT_FILER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Louis Chua",
            None,
            None,
            None,
            seeded_reports.chua.id,
        ),
        (
            report_id,
            2,
            ParticipantRole.READER,
            ParticipantRoleSource.ASKER_RULES,
            3,
            "Mr Gerald Giam",
            None,
            None,
            None,
            seeded_reports.giam.id,
        ),
        (
            report_id,
            3,
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            4,
            "Mr Pritam Singh",
            None,
            None,
            None,
            seeded_reports.singh.id,
        ),
        (
            report_id,
            4,
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            5,
            "Mr Nobody Known",
            None,
            None,
            None,
            None,
        ),
        (
            report_id,
            5,
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_LABEL,
            6,
            _MINISTER_OF_HEALTH_LABEL,
            None,
            _MINISTER_OF_HEALTH,
            OfficeSource.LABEL_IN_REPORT,
            seeded_reports.ong.id,
        ),
        (
            report_id,
            6,
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            7,
            "Dr Tan See Leng",
            None,
            _MINISTER_OF_MANPOWER,
            OfficeSource.HEADER_IN_REPORT,
            seeded_reports.tan.id,
        ),
        (
            report_id,
            7,
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            8,
            "Mr Chee Hong Tat",
            None,
            _SENIOR_MINISTER_OF_STATE,
            OfficeSource.ATTENDANCE_LIST,
            seeded_reports.chee.id,
        ),
    ]


def _get_written_rows(seeded_reports: _SeededReports) -> list[tuple]:
    return [
        (
            seeded_reports.written_report.id,
            1,
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Gerald Giam",
            None,
            None,
            None,
            seeded_reports.giam.id,
        ),
        (
            seeded_reports.written_report.id,
            2,
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            2,
            "Mr Ong Ye Kung",
            None,
            _MINISTER_OF_HEALTH,
            OfficeSource.LABEL_SAME_DAY,
            seeded_reports.ong.id,
        ),
    ]


def _get_later_written_rows(seeded_reports: _SeededReports) -> list[tuple]:
    return [
        (
            seeded_reports.later_written_report.id,
            1,
            ParticipantRole.ASKER,
            ParticipantRoleSource.ASKER_RULES,
            1,
            "Mr Pritam Singh",
            None,
            None,
            None,
            seeded_reports.singh.id,
        ),
        (
            seeded_reports.later_written_report.id,
            2,
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            2,
            "Mr Ong Ye Kung",
            None,
            _MINISTER_OF_HEALTH,
            OfficeSource.PARLIAMENT_GUESS,
            seeded_reports.ong.id,
        ),
        (
            seeded_reports.later_written_report.id,
            3,
            ParticipantRole.ANSWERER,
            ParticipantRoleSource.OFFICE_ON_THE_DAY,
            3,
            "Mr Chee Hong Tat",
            None,
            _SENIOR_MINISTER_OF_STATE,
            OfficeSource.ATTENDANCE_LIST,
            seeded_reports.chee.id,
        ),
    ]


def _get_planned_rows(seeded_reports: _SeededReports) -> list[tuple]:
    return (
        _get_oral_rows(seeded_reports)
        + _get_written_rows(seeded_reports)
        + _get_later_written_rows(seeded_reports)
    )


def _get_planned_states(seeded_reports: _SeededReports) -> list[tuple]:
    return [
        (seeded_reports.annex_report.id, QuestionState.NOT_A_QUESTION, "Annex A", None)
    ]


def _get_stored_rows(session: Session) -> list[tuple]:
    session.expire_all()
    return sorted(
        (
            report_participant.report_id,
            report_participant.ordinal,
            report_participant.role,
            report_participant.role_source,
            report_participant.first_ordinal,
            report_participant.printed_name,
            report_participant.answering_for_printed,
            report_participant.office_printed,
            report_participant.office_source,
            report_participant.speaker_id,
        )
        for report_participant in session.exec(select(ReportParticipant)).all()
    )


def _get_stored_states(session: Session) -> list[tuple]:
    session.expire_all()
    return sorted(
        (
            report_question_state.report_id,
            report_question_state.state,
            report_question_state.printed_text,
            report_question_state.first_ordinal,
        )
        for report_question_state in session.exec(select(ReportQuestionState)).all()
    )


@pytest.fixture
def log_recorder(
    scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> _LogRecorder:
    recorder = _LogRecorder()
    monkeypatch.setattr(apply_report_participants_script, "engine", scratch_engine)
    monkeypatch.setattr(apply_report_participants_script, "logger", recorder)
    return recorder


def test_dry_run_logs_the_plan_and_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    _seed_reports(scratch_session)

    apply_report_participants([], is_commit=False)

    assert f"Parliament 14: {_COUNTS_LOG}" in log_recorder.messages
    assert f"All: {_COUNTS_LOG}" in log_recorder.messages
    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Dry run: nothing written"
    assert _get_stored_rows(scratch_session) == []
    assert _get_stored_states(scratch_session) == []


def test_commit_writes_the_planned_rows_of_the_question_reports_only(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)

    apply_report_participants([], is_commit=True)

    assert _PLAN_LOG in log_recorder.messages
    assert log_recorder.messages[-1] == "Committed"
    assert _get_stored_rows(scratch_session) == _get_planned_rows(seeded_reports)
    assert _get_stored_states(scratch_session) == _get_planned_states(seeded_reports)


def test_commit_on_a_rerun_leaves_the_same_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    apply_report_participants([], is_commit=True)

    apply_report_participants([], is_commit=True)

    assert log_recorder.messages.count(_PLAN_LOG) > 1
    assert _get_stored_rows(scratch_session) == _get_planned_rows(seeded_reports)
    assert _get_stored_states(scratch_session) == _get_planned_states(seeded_reports)


def test_commit_with_report_ids_leaves_other_reports_rows_alone(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    apply_report_participants([], is_commit=True)
    written_report_participant = next(
        report_participant
        for report_participant in scratch_session.exec(select(ReportParticipant)).all()
        if report_participant.report_id == seeded_reports.written_report.id
        and report_participant.role == ParticipantRole.ASKER
    )
    written_report_participant.printed_name = _HAND_EDITED_NAME
    scratch_session.commit()

    apply_report_participants([seeded_reports.oral_report.id], is_commit=True)

    hand_edited_row = (
        seeded_reports.written_report.id,
        1,
        ParticipantRole.ASKER,
        ParticipantRoleSource.ASKER_RULES,
        1,
        _HAND_EDITED_NAME,
        None,
        None,
        None,
        seeded_reports.giam.id,
    )
    assert _get_stored_rows(scratch_session) == (
        _get_oral_rows(seeded_reports)
        + [hand_edited_row, _get_written_rows(seeded_reports)[1]]
        + _get_later_written_rows(seeded_reports)
    )


def test_commit_of_a_report_that_is_not_a_question_writes_nothing(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)

    apply_report_participants([seeded_reports.motion_report.id], is_commit=True)

    assert _EMPTY_PLAN_LOG in log_recorder.messages
    assert _get_stored_rows(scratch_session) == []
    assert _get_stored_states(scratch_session) == []


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
        populate_report_participants(
            scratch_session,
            [
                seeded_reports.oral_report.id,
                seeded_reports.written_report.id,
                seeded_reports.later_written_report.id,
                seeded_reports.annex_report.id,
                seeded_reports.motion_report.id,
            ],
        )
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert any(
        statement.startswith("INSERT INTO report_participant")
        for statement in statements
    )
    assert any(
        statement.startswith("INSERT INTO report_question_state")
        for statement in statements
    )
    assert not [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("DELETE")
    ]
    assert _get_stored_rows(scratch_session) == _get_planned_rows(seeded_reports)
    assert _get_stored_states(scratch_session) == _get_planned_states(seeded_reports)


def test_commit_refuses_the_protected_port_before_any_row_is_written(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)
    monkeypatch.setattr(
        apply_report_participants_script,
        "settings",
        SimpleNamespace(database_url=_PROTECTED_DATABASE_URL),
    )

    with pytest.raises(HansardWriteTargetError, match="local port 5432"):
        apply_report_participants([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []
    assert _get_stored_states(scratch_session) == []


def test_commit_refuses_a_short_participant_delete_count_and_keeps_the_rows(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    apply_report_participants([], is_commit=True)
    real_delete_by_report_ids = CRUDReportParticipant.delete_by_report_ids

    def delete_by_report_ids_one_short(
        self: CRUDReportParticipant, report_ids: list[int]
    ) -> int:
        return real_delete_by_report_ids(self, report_ids) - 1

    monkeypatch.setattr(
        CRUDReportParticipant, "delete_by_report_ids", delete_by_report_ids_one_short
    )

    with pytest.raises(
        HansardWriteCheckError, match="Deleted 11 report participants, read 12"
    ):
        apply_report_participants([], is_commit=True)

    assert _get_stored_rows(scratch_session) == _get_planned_rows(seeded_reports)


def test_commit_refuses_a_short_state_delete_count_and_keeps_the_rows(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    apply_report_participants([], is_commit=True)
    real_delete_by_report_ids = CRUDReportQuestionState.delete_by_report_ids

    def delete_by_report_ids_one_short(
        self: CRUDReportQuestionState, report_ids: list[int]
    ) -> int:
        return real_delete_by_report_ids(self, report_ids) - 1

    monkeypatch.setattr(
        CRUDReportQuestionState, "delete_by_report_ids", delete_by_report_ids_one_short
    )

    with pytest.raises(
        HansardWriteCheckError, match="Deleted 0 report question states, read 1"
    ):
        apply_report_participants([], is_commit=True)

    assert _get_stored_rows(scratch_session) == _get_planned_rows(seeded_reports)
    assert _get_stored_states(scratch_session) == _get_planned_states(seeded_reports)


def test_commit_refuses_stored_rows_that_differ_from_the_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)
    real_add_many = CRUDReportParticipant.add_many

    def add_many_one_short(
        self: CRUDReportParticipant, report_participants: list[ReportParticipant]
    ) -> None:
        real_add_many(self, report_participants[:-1])

    monkeypatch.setattr(CRUDReportParticipant, "add_many", add_many_one_short)

    with pytest.raises(
        HansardWriteCheckError,
        match="Parliament 14: stored report participants by role",
    ):
        apply_report_participants([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []
    assert _get_stored_states(scratch_session) == []


def test_commit_refuses_stored_states_that_differ_from_the_plan(
    scratch_session: Session,
    log_recorder: _LogRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_reports(scratch_session)

    def add_many_none(
        self: CRUDReportQuestionState,
        report_question_states: list[ReportQuestionState],
    ) -> None:
        return None

    monkeypatch.setattr(CRUDReportQuestionState, "add_many", add_many_none)

    with pytest.raises(
        HansardWriteCheckError, match="Parliament 14: stored report question states"
    ):
        apply_report_participants([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []


def test_commit_refuses_a_report_asker_row_that_differs_from_the_asker_participants(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    doctored_report_asker = next(
        report_asker
        for report_asker in scratch_session.exec(select(ReportAsker)).all()
        if report_asker.report_id == seeded_reports.oral_report.id
        and report_asker.printed_name == "Mr Pritam Singh"
    )
    doctored_report_asker.printed_name = _HAND_EDITED_NAME
    scratch_session.commit()

    with pytest.raises(
        HansardWriteCheckError,
        match=f"Report {seeded_reports.oral_report.id}: report participants hold askers",
    ):
        apply_report_participants([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []
    assert _get_stored_states(scratch_session) == []


def test_commit_refuses_a_report_asker_reader_that_differs_from_the_reader_participants(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    doctored_report_asker = next(
        report_asker
        for report_asker in scratch_session.exec(select(ReportAsker)).all()
        if report_asker.report_id == seeded_reports.oral_report.id
        and report_asker.reader_printed_name is not None
    )
    doctored_report_asker.reader_printed_name = _HAND_EDITED_NAME
    scratch_session.commit()

    with pytest.raises(
        HansardWriteCheckError,
        match=f"Report {seeded_reports.oral_report.id}: report participants hold readers",
    ):
        apply_report_participants([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []


def test_commit_refuses_a_report_with_participants_and_no_report_asker_rows(
    scratch_session: Session, log_recorder: _LogRecorder
) -> None:
    seeded_reports = _seed_reports(scratch_session)
    CRUDReportAsker(scratch_session).delete_by_report_ids(
        [seeded_reports.written_report.id]
    )
    scratch_session.commit()

    with pytest.raises(
        HansardWriteCheckError,
        match=f"Report {seeded_reports.written_report.id}: report participants hold askers",
    ):
        apply_report_participants([], is_commit=True)

    assert _get_stored_rows(scratch_session) == []


def test_parliament_guess_skips_a_member_the_attendance_lists_and_keeps_one_it_does_not(
    scratch_session: Session,
) -> None:
    singh = _build_speaker("Pritam Singh")
    listed_report = _build_report(
        "listed",
        ReportType.WRITTEN_ANSWER,
        _FIRST_SITTING_DATE,
        "Listed Sitting",
        None,
    )
    unlisted_report = _build_report(
        "unlisted",
        ReportType.WRITTEN_ANSWER,
        _SECOND_SITTING_DATE,
        "Unlisted Sitting",
        None,
    )
    office_report = _build_report(
        "office",
        ReportType.WRITTEN_ANSWER_NOT_AVAILABLE,
        _THIRD_SITTING_DATE,
        "Annex B",
        None,
    )
    sitting = Sitting(
        sitting_date="2-4-2025",
        parlement_no=_PARLIAMENT_NUMBER,
        markdown_content="PRESENT:\nMr Pritam Singh (Aljunied).\n",
    )
    scratch_session.add_all(
        [singh, listed_report, unlisted_report, office_report, sitting]
    )
    scratch_session.flush()
    scratch_session.add(
        Attendance(
            sitting_id=sitting.id,
            speaker_name="Pritam Singh",
            is_present=True,
            speaker_id=singh.id,
        )
    )
    scratch_session.add_all(
        [
            _build_speech(
                listed_report,
                1,
                "Mr Pritam Singh",
                singh.id,
                SpeechKind.SPEECH,
                "To ask the Minister for Health how many clinics opened.",
            ),
            _build_speech(
                unlisted_report,
                1,
                "Mr Pritam Singh",
                singh.id,
                SpeechKind.SPEECH,
                "To ask the Minister for Health how many clinics will open.",
            ),
            _build_speech(
                office_report,
                1,
                "The Minister of State for Finance (Mr Pritam Singh)",
                singh.id,
                SpeechKind.SPEECH,
                "The figures are annexed.",
            ),
        ]
    )
    scratch_session.commit()

    plan = get_report_participant_plan(
        scratch_session, [listed_report.id, unlisted_report.id, office_report.id]
    )

    assert [
        (
            report_participant.report_id,
            report_participant.office_printed,
            report_participant.office_source,
        )
        for report_participant in plan.report_participants
    ] == [
        (listed_report.id, None, None),
        (
            unlisted_report.id,
            "The Minister of State for Finance",
            OfficeSource.PARLIAMENT_GUESS,
        ),
    ]
