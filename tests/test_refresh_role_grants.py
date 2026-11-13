from collections.abc import Iterator
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, event
from sqlmodel import Session, SQLModel, select

import populate.minutes as minutes_step
import populate.refresh_runs as refresh_runs
from database.ministry import Ministry
from database.minutes import Minutes
from database.report import Report
from database.seat_holding import SeatHolding
from database.sitting import Sitting
from database.speaker import Speaker
from database.speech import Speech
from enums import (
    MinutesStatus,
    RefreshRunStatus,
    ReportType,
    SpeechKind,
)
from populate.attendance_offices import populate_attendance_offices
from populate.bill_speakers import populate_bill_speakers
from populate.office_printed_ranges import populate_office_printed_ranges
from populate.speaker_links import link_speakers_by_report_ids_and_sitting_ids
from schemas.minutes_response import MinutesResponse
from services.refresh import SINGAPORE_TIMEZONE
from settings import settings
from tests.bill_seed import (
    seed_bill_report,
    seed_speaker,
    seed_speech,
    seed_stored_bill,
)
from tests.division_seed import add_division_report
from tests.refresh_fixtures import (
    FakeParliament,
    build_live_index_page,
    build_live_index_row,
    seed_stored,
)
from tests.refresh_role_grants import (
    RoleGrants,
    get_grant_violations,
    get_role_grants,
    get_write_role_blocks,
)
from utils.data_files import get_ministry_names

_TABLE_NAMES = frozenset(table.name for table in SQLModel.metadata.sorted_tables)
_FIRST_READING_LINE = "Bill read a First time."
_THIRD_READING_LINE = "Bill read a Third time and passed."
_FIRST_DATE = datetime(2025, 1, 15)
_SECOND_DATE = datetime(2025, 2, 19)
_THIRD_DATE = datetime(2025, 3, 5)
_NEW_TABLES = (
    "bill",
    "billreport",
    "billkey",
    "billreportspeaker",
    "billstageline",
)
_NEW_SEQUENCES = (
    "bill_id_seq",
    "billreport_id_seq",
    "billkey_id_seq",
    "billreportspeaker_id_seq",
    "billstageline_id_seq",
)
_NEW_BILL_COLUMNS = ("title", "last_sitting_date", "is_passed")
_VERIFICATION_FUNCTIONS = (
    "has_table_privilege",
    "has_column_privilege",
    "has_sequence_privilege",
)
_MINUTES_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures" / "minutes"
_MINUTES_DIVISION_TEXT_FIXTURE = (
    Path(__file__).parent / "division_fixtures" / "minutes_2021_10_04.txt"
)
_MINUTES_SITTING_DATE = date(2018, 1, 10)
_MINUTES_FILE_ID = "minutes-file-id"
_MINUTES_FILE_NAME = "VP-11Jan2018.pdf"
_MINUTES_FILE_NUMBER = 57
_ATTACHED_FILE_ADDRESS = "20240910/annex-Refresh Test.pdf"
_ATTACHED_FILE_ID = 9001
_DIVISION_REPORT_ID = "motion-2481#"
_DIVISION_LINE = "<p>The House divided: Ayes, 10; Noes, 3.</p>"
_CORRECTION_TITLE_START = "Addendum to "
_CHANGED_OFFICE_ENTRY_LINE = (
    "Mr Chee Hong Tat (Bishan-Toa Payoh), Minister for Transport."
)
_CITED_TITLE = "Title A"
_CITED_VOLUME_NUMBER = 94
_CITATION = (
    f'[Please refer to "{_CITED_TITLE}", Official Report, 3 March 2020, Volume 94, '
    "Issue No 12, Written Answers section]"
)
_LEAVE_MEMBER_NAME = "Mr Chee Hong Tat"
_LEAVE_MEMBER_SPEAKER_NAME = "Chee Hong Tat"
_PREVIOUS_PARLIAMENT_NUMBER = 14
_EARLIER_SEAT_DATE = date(2024, 1, 1)
_DAYS_AFTER_NEW_SITTING = 2
_SINGAPORE_RUN_HOUR = 4
_REFRESH_STATEMENT_STARTS = (
    "INSERT INTO refresh_run ",
    "INSERT INTO hansardwebsiteresponse ",
    "INSERT INTO report ",
    "INSERT INTO speech ",
    "INSERT INTO hansardsittingdateresponse ",
    "INSERT INTO sitting ",
    "INSERT INTO attendance ",
    "UPDATE speech SET speaker_id",
    "UPDATE attendance SET speaker_id",
    "INSERT INTO report_asker ",
    "INSERT INTO report_participant ",
    "INSERT INTO report_question_state ",
    "INSERT INTO attendance_office ",
    "INSERT INTO report_put_to ",
    "INSERT INTO office_title_ministry ",
    "INSERT INTO office_printed_range ",
    "UPDATE office_printed_range SET",
    "INSERT INTO attached_file ",
    "INSERT INTO attached_file_pointer ",
    "UPDATE attached_file_pointer SET",
    "INSERT INTO leave_period ",
    "INSERT INTO leave_period_printing ",
    "INSERT INTO seat_holding ",
    "UPDATE seat_holding SET",
    "INSERT INTO division ",
    "INSERT INTO division_vote ",
    "INSERT INTO minutes ",
    "INSERT INTO minutes_index_capture ",
    "UPDATE minutes SET",
    "INSERT INTO minutes_division ",
    "INSERT INTO division_party_count ",
    "VACUUM (ANALYZE) speech",
    "VACUUM (ANALYZE) report",
    "VACUUM (ANALYZE) attendance",
    "INSERT INTO report_link ",
    "UPDATE refresh_run SET",
)


class _StatementRecorder:
    def __init__(self):
        self.statements: list[str] = []

    def record_statement(
        self,
        connection: Connection,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        self.statements.append(statement)


def _seed_scenario(session: Session) -> list[int]:
    speaker_id = seed_speaker(session, "Ms A")
    stored_report_id = seed_bill_report(
        session, "alpha-1", ReportType.BILL, _FIRST_DATE, "Alpha Bill", []
    )
    seed_stored_bill(
        session,
        "Alpha Bill",
        [stored_report_id],
        _FIRST_DATE,
        _FIRST_DATE,
        False,
        "alpha-1",
    )
    alpha_2_id = seed_bill_report(
        session,
        "alpha-2",
        ReportType.BILL,
        _SECOND_DATE,
        "Alpha Bill",
        [_THIRD_READING_LINE],
    )
    seed_speech(
        session, alpha_2_id, 2, "Ms A", speaker_id, SpeechKind.SPEECH, "I agree."
    )
    beta_1_id = seed_bill_report(
        session, "beta-1", ReportType.BILL, _THIRD_DATE, "Beta Bill", []
    )
    seed_speech(
        session,
        beta_1_id,
        1,
        None,
        None,
        SpeechKind.PROCEDURAL,
        _FIRST_READING_LINE,
    )
    seed_speech(
        session, beta_1_id, 2, "Ms A", speaker_id, SpeechKind.SPEECH, "I support it."
    )
    adjourn_1_id = seed_bill_report(
        session, "adjourn-1", ReportType.BILL, _THIRD_DATE, "ADJOURNMENT", []
    )
    return [alpha_2_id, beta_1_id, adjourn_1_id]


@pytest.fixture
def recorded_statements(
    scratch_engine: Engine, scratch_session: Session
) -> Iterator[list[str]]:
    report_ids = _seed_scenario(scratch_session)
    recorder = _StatementRecorder()
    event.listen(scratch_engine, "before_cursor_execute", recorder.record_statement)
    try:
        populate_bill_speakers(scratch_session, report_ids)
        scratch_session.commit()
    finally:
        event.remove(scratch_engine, "before_cursor_execute", recorder.record_statement)
    yield recorder.statements


def _seed_stored_offices(session: Session) -> None:
    stored_sitting_ids = [
        sitting.id
        for sitting in session.exec(select(Sitting)).all()
        if sitting.id is not None
    ]
    link_speakers_by_report_ids_and_sitting_ids(session, [], stored_sitting_ids)
    populate_attendance_offices(session, stored_sitting_ids)
    populate_office_printed_ranges(session, stored_sitting_ids)
    session.add_all([Ministry(name=name) for name in get_ministry_names()])


def _seed_earlier_seat_holding(session: Session) -> None:
    chee = session.exec(
        select(Speaker)
        .where(Speaker.name == _LEAVE_MEMBER_SPEAKER_NAME)
        .where(Speaker.parliament_number == _PREVIOUS_PARLIAMENT_NUMBER)
    ).one()
    assert chee.id is not None
    session.add(
        SeatHolding(
            division_key="bishan toa payoh",
            location_name="Bishan-Toa Payoh",
            first_sitting_date=_EARLIER_SEAT_DATE,
            last_sitting_date=_EARLIER_SEAT_DATE,
            sitting_count=1,
            speaker_id=chee.id,
        )
    )


def _seed_minutes(session: Session) -> None:
    add_division_report(
        session,
        "MINUTES-REPORT",
        datetime.combine(_MINUTES_SITTING_DATE, datetime.min.time()),
    )
    session.add(
        Minutes(sitting_date=_MINUTES_SITTING_DATE, status=MinutesStatus.NOT_YET_LISTED)
    )


def _add_cited_report(
    session: Session, report_id: str, sitting_date: datetime, title: str
) -> Report:
    report = add_division_report(session, report_id, sitting_date)
    report.volume_number = _CITED_VOLUME_NUMBER
    report.original_title = title
    report.title = title
    report.report_type = ReportType.ORAL_ANSWER
    return report


def _seed_citation(session: Session) -> None:
    source = _add_cited_report(
        session, "SOURCE#1", datetime(2020, 3, 10), "Source title"
    )
    _add_cited_report(session, "TARGET#1", datetime(2020, 3, 3), _CITED_TITLE)
    assert source.id is not None
    session.add(
        Speech(
            ordinal=1,
            speaker="Mr A",
            transcript=_CITATION,
            sitting_date=source.sitting_date,
            report_type=source.report_type,
            report_id=source.id,
        )
    )


def _set_new_sitting_rows(fake_parliament: FakeParliament) -> None:
    first_search_result = fake_parliament.new_search_results[0]
    first_search_result["title"] = (
        _CORRECTION_TITLE_START + first_search_result["title"]
    )
    fake_parliament.report_id_to_topic[first_search_result["reportId"]]["resultHTML"][
        "content"
    ] += (
        f'<p><a href="/search/search/download?value={_ATTACHED_FILE_ADDRESS}">'
        "Annex A</a></p>"
    )
    fake_parliament.report_id_to_topic[_DIVISION_REPORT_ID]["resultHTML"][
        "content"
    ] += _DIVISION_LINE
    fake_parliament.new_sitting["annexureList"] = [
        {
            "annexureID": _ATTACHED_FILE_ID,
            "annexureTitle": "Annex A",
            "filePath": f"d:/apps/reports/solr_files/{_ATTACHED_FILE_ADDRESS}",
            "fileName": "annex-Refresh Test.pdf",
            "sectionType": None,
            "sittingDate": None,
            "file": None,
        }
    ]
    fake_parliament.new_sitting["attendanceList"][0]["mpName"] = (
        _CHANGED_OFFICE_ENTRY_LINE
    )
    fake_parliament.new_sitting["ptbaList"] = [
        {
            "mpName": _LEAVE_MEMBER_NAME,
            "from": "10 Sep",
            "to": "12 Sep",
            "endDtFlag": False,
        }
    ]
    fake_parliament.minutes_index_page = build_live_index_page(
        [
            build_live_index_row(
                _MINUTES_SITTING_DATE,
                _MINUTES_FILE_NUMBER,
                _MINUTES_FILE_ID,
                _MINUTES_FILE_NAME,
            )
        ]
    )
    file_url = f"{settings.minutes_media_url}/{_MINUTES_FILE_ID}/{_MINUTES_FILE_NAME}"
    fake_parliament.file_url_to_response[file_url] = MinutesResponse(
        url=file_url,
        status_code=200,
        content=(
            _MINUTES_FIXTURE_DIRECTORY / "vp-10jan18-first-pages.pdf"
        ).read_bytes(),
    )


@pytest.fixture
def fake_parliament(monkeypatch: pytest.MonkeyPatch) -> FakeParliament:
    fake_parliament = FakeParliament()
    monkeypatch.setattr(
        refresh_runs,
        "get_all_hansard_search_results",
        fake_parliament.get_all_hansard_search_results,
    )
    monkeypatch.setattr(
        refresh_runs,
        "get_hansard_report_response",
        fake_parliament.get_hansard_report_response,
    )
    monkeypatch.setattr(
        refresh_runs,
        "get_hansard_topic_response_async",
        fake_parliament.get_hansard_topic_response_async,
    )
    monkeypatch.setattr(
        minutes_step,
        "get_minutes_index_response",
        fake_parliament.get_minutes_index_response,
    )
    monkeypatch.setattr(
        minutes_step,
        "get_minutes_file_response",
        fake_parliament.get_minutes_file_response,
    )
    monkeypatch.setattr(
        minutes_step,
        "get_minutes_pdf_text",
        lambda content: _MINUTES_DIVISION_TEXT_FIXTURE.read_text(encoding="utf-8"),
    )
    monkeypatch.setattr("populate.report_links.get_report_link_title_corrections", list)
    monkeypatch.setattr(settings, "telegram_bot_token", None)
    monkeypatch.setattr(settings, "telegram_chat_id", None)
    monkeypatch.setattr(settings, "healthchecks_ping_url", None)
    return fake_parliament


@pytest.fixture
def recorded_refresh_statements(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
) -> Iterator[list[str]]:
    seed_stored(scratch_session)
    _seed_stored_offices(scratch_session)
    _seed_earlier_seat_holding(scratch_session)
    _seed_minutes(scratch_session)
    _seed_citation(scratch_session)
    scratch_session.commit()
    _set_new_sitting_rows(fake_parliament)
    run_date = fake_parliament.new_sitting_date + timedelta(
        days=_DAYS_AFTER_NEW_SITTING
    )
    now = datetime(
        run_date.year,
        run_date.month,
        run_date.day,
        _SINGAPORE_RUN_HOUR,
        tzinfo=SINGAPORE_TIMEZONE,
    ).astimezone(timezone.utc)
    recorder = _StatementRecorder()
    event.listen(scratch_engine, "before_cursor_execute", recorder.record_statement)
    try:
        status = refresh_runs.populate_refresh_runs(scratch_session, now, None)
    finally:
        event.remove(scratch_engine, "before_cursor_execute", recorder.record_statement)
    assert status == RefreshRunStatus.SUCCEEDED
    yield recorder.statements


def _get_role_grants() -> RoleGrants:
    return get_role_grants(get_write_role_blocks()[0])


def test_the_scenario_sends_the_statements_the_grants_must_cover(
    recorded_statements: list[str],
) -> None:
    for statement_start in (
        "INSERT INTO bill ",
        "INSERT INTO billkey",
        "INSERT INTO billreport ",
        "UPDATE bill SET",
    ):
        assert any(
            statement.startswith(statement_start) for statement in recorded_statements
        )
    assert any(
        "FROM billreport" in statement or "JOIN billreport" in statement
        for statement in recorded_statements
    )


def test_the_stage_statements_pass_the_grants_in_the_doc(
    recorded_statements: list[str],
) -> None:
    assert (
        get_grant_violations(recorded_statements, _TABLE_NAMES, _get_role_grants())
        == []
    )


def test_dropping_is_passed_from_the_column_grant_fails(
    recorded_statements: list[str],
) -> None:
    role_grants = _get_role_grants()
    weakened_grants = replace(
        role_grants,
        column_privileges=role_grants.column_privileges - {"UPDATE bill.is_passed"},
    )

    violations = get_grant_violations(
        recorded_statements, _TABLE_NAMES, weakened_grants
    )

    assert "UPDATE on bill.is_passed" in violations


def test_dropping_a_sequence_grant_fails(recorded_statements: list[str]) -> None:
    role_grants = _get_role_grants()
    weakened_grants = replace(
        role_grants,
        sequence_usages=role_grants.sequence_usages - {"billkey_id_seq"},
    )

    violations = get_grant_violations(
        recorded_statements, _TABLE_NAMES, weakened_grants
    )

    assert "USAGE on billkey_id_seq" in violations


def test_a_delete_statement_fails() -> None:
    role_grants = _get_role_grants()

    assert get_grant_violations(
        ["DELETE FROM billkey WHERE billkey.id = 1"], _TABLE_NAMES, role_grants
    )
    assert get_grant_violations(["TRUNCATE billkey"], _TABLE_NAMES, role_grants)


def test_the_parser_reads_the_existing_and_new_grants() -> None:
    role_grants = _get_role_grants()

    assert "SELECT billkey" in role_grants.table_privileges
    assert "INSERT billreportspeaker" in role_grants.table_privileges
    assert "UPDATE speech.speaker_id" in role_grants.column_privileges
    assert "UPDATE bill.title" in role_grants.column_privileges
    assert "billstageline_id_seq" in role_grants.sequence_usages
    assert "SELECT refresh_run.id" not in role_grants.column_privileges


def test_the_doc_grants_no_delete_and_only_three_bill_columns() -> None:
    role_grants = _get_role_grants()

    assert not [
        privilege
        for privilege in role_grants.table_privileges | role_grants.column_privileges
        if privilege.startswith("DELETE")
    ]
    assert {
        column_privilege
        for column_privilege in role_grants.column_privileges
        if column_privilege.startswith("UPDATE bill.")
    } == {f"UPDATE bill.{column}" for column in _NEW_BILL_COLUMNS}


def test_the_verification_query_names_every_granted_bill_object() -> None:
    verification_query = get_write_role_blocks()[1]

    for name in _NEW_TABLES + _NEW_SEQUENCES + _NEW_BILL_COLUMNS:
        assert f"'{name}'" in verification_query
    for function_name in _VERIFICATION_FUNCTIONS:
        assert function_name in verification_query


def test_the_refresh_run_sends_a_write_from_every_step(
    recorded_refresh_statements: list[str],
) -> None:
    for statement_start in _REFRESH_STATEMENT_STARTS:
        assert any(
            statement.startswith(statement_start)
            for statement in recorded_refresh_statements
        ), statement_start


def test_the_refresh_run_statements_pass_the_grants_in_the_doc(
    recorded_refresh_statements: list[str],
) -> None:
    assert (
        get_grant_violations(
            recorded_refresh_statements, _TABLE_NAMES, _get_role_grants()
        )
        == []
    )


def test_dropping_the_speech_speaker_id_grant_fails_the_refresh_run(
    recorded_refresh_statements: list[str],
) -> None:
    role_grants = _get_role_grants()
    weakened_grants = replace(
        role_grants,
        column_privileges=role_grants.column_privileges - {"UPDATE speech.speaker_id"},
    )

    violations = get_grant_violations(
        recorded_refresh_statements, _TABLE_NAMES, weakened_grants
    )

    assert "UPDATE on speech.speaker_id" in violations


def test_dropping_maintain_on_speech_fails_the_refresh_run(
    recorded_refresh_statements: list[str],
) -> None:
    role_grants = _get_role_grants()
    weakened_grants = replace(
        role_grants,
        table_privileges=role_grants.table_privileges - {"MAINTAIN speech"},
    )

    violations = get_grant_violations(
        recorded_refresh_statements, _TABLE_NAMES, weakened_grants
    )

    assert violations == ["MAINTAIN on speech"]


def test_attendance_inserts_need_the_sequence_named_in_the_doc(
    recorded_refresh_statements: list[str],
) -> None:
    role_grants = _get_role_grants()
    weakened_grants = replace(
        role_grants,
        sequence_usages=role_grants.sequence_usages - {"sittingattendance_id_seq"},
    )

    violations = get_grant_violations(
        recorded_refresh_statements, _TABLE_NAMES, weakened_grants
    )

    assert violations == ["USAGE on sittingattendance_id_seq"]
