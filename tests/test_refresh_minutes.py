import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from loguru import logger
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, func, select

import populate.minutes as minutes_step
import refresh_minutes
from database.division import Division
from database.division_party_count import DivisionPartyCount
from database.division_vote import DivisionVote
from database.minutes import Minutes, MinutesIndexCapture
from database.minutes_division import MinutesDivision
from database.refresh_run import RefreshRun
from database.report import Report
from enums import (
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    MinutesFileFormat,
    MinutesIndexSource,
    MinutesStatus,
)
from exceptions import (
    HansardGatewayError,
    HansardMinutesIndexError,
    HansardSettingError,
    HansardWriteCheckError,
)
from populate.minutes_divisions import UNREAD_DIVISION_STATUS_NOTE
from schemas.minutes_response import MinutesResponse
from services.refresh import SINGAPORE_TIMEZONE
from settings import settings
from tests.division_seed import add_division_report
from tests.refresh_fixtures import (
    FakeParliament,
    build_live_index_page,
    build_live_index_row,
    seed_stored,
)
from tests.refresh_role_grants import (
    get_grant_violations,
    get_role_grants,
    get_write_role_blocks,
)

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures"
_PDF_FIXTURE = _FIXTURE_DIRECTORY / "minutes" / "vp-10jan18-first-pages.pdf"
_DIVISION_TEXT_FIXTURE = _FIXTURE_DIRECTORY / "minutes_2021_10_04.txt"
_TODAY = date(2018, 2, 1)
_NOW = datetime(
    _TODAY.year, _TODAY.month, _TODAY.day, 5, 30, tzinfo=SINGAPORE_TIMEZONE
).astimezone(timezone.utc)
_FIRST_DATE = date(2018, 1, 10)
_SECOND_DATE = date(2018, 1, 11)
_THIRD_DATE = date(2018, 1, 12)
_RECHECK_WINDOW_DAYS = 14
_BOT_TOKEN = "test-bot-token"
_CHAT_ID = "test-chat"
_ACCEPTED_STATUS = 202
_NOT_FOUND_STATUS = 404
_TABLE_NAMES = frozenset(table.name for table in SQLModel.metadata.sorted_tables)
_MINUTES_WRITE_STATEMENT_STARTS = (
    "INSERT INTO minutes ",
    "INSERT INTO minutes_index_capture ",
    "INSERT INTO minutes_division ",
    "INSERT INTO division_vote ",
    "INSERT INTO division_party_count ",
    "UPDATE minutes SET",
)
_INDEX_SKIPPED_MESSAGE_END = (
    ". The run did not fail, and the next run reads the page again."
)
_UNREADABLE_DIVISION_TEXT = "On Question put, the House divided."
_MINUTES_DIVISION_ROW_COUNT = 2
_HANSARD_ONLY_PRINTED_COUNTS = "The House divided: Ayes, 1; Noes, 1."
_MINUTES_STEP_ALLOWED_STATEMENTS = frozenset(
    {
        ("SELECT", "minutes"),
        ("SELECT", "minutes_index_capture"),
        ("SELECT", "report"),
        ("INSERT", "minutes"),
        ("INSERT", "minutes_index_capture"),
        ("INSERT", "division"),
        ("INSERT", "minutes_division"),
        ("INSERT", "division_vote"),
        ("SELECT", "division"),
        ("SELECT", "minutes_division"),
        ("SELECT", "division_vote"),
        ("INSERT", "division_party_count"),
        ("SELECT", "division_party_count"),
        ("SELECT", "speaker"),
        ("SELECT", "partyaffiliation"),
        ("UPDATE", "minutes"),
    }
)
_MINUTES_STEP_UPDATE_COLUMNS = frozenset(
    {
        "status",
        "index_source",
        "index_capture_id",
        "printed_label",
        "printed_parliament",
        "file_url",
        "archive_timestamp",
        "file_format",
        "sha256",
        "size_bytes",
        "file_bytes",
        "fetched_at",
        "extracted_text",
        "status_note",
    }
)
_STATEMENT_VERB_PATTERN = re.compile(
    r"^\s*(SELECT|INSERT|UPDATE|DELETE|TRUNCATE|GRANT)\b", re.IGNORECASE
)
_UPDATE_TABLE_PATTERN = re.compile(r'^\s*UPDATE\s+"?([a-z_]+)"?', re.IGNORECASE)
_INSERT_TABLE_PATTERN = re.compile(r'^\s*INSERT\s+INTO\s+"?([a-z_]+)"?', re.IGNORECASE)
_READ_TABLE_PATTERN = re.compile(r'\b(?:FROM|JOIN)\s+"?([a-z_]+)"?', re.IGNORECASE)
_SET_CLAUSE_PATTERN = re.compile(r"\bSET\s+(.*?)\s+WHERE\b", re.DOTALL | re.IGNORECASE)
_SET_COLUMN_PATTERN = re.compile(r"(\w+)\s*=\s*%\(")
_GRANTED_UPDATE_STATEMENT = "UPDATE minutes SET status=%(status)s, sha256=%(sha256)s WHERE minutes.id = %(id_1)s AND minutes.status = %(status_1)s"


@dataclass
class _AlertRecorder:
    messages: list[str] = field(default_factory=list)

    def send_telegram_message(self, bot_token: str, chat_id: str, text: str) -> None:
        self.messages.append(text)


class _StatementRecorder:
    def __init__(self):
        self.statements: list[str] = []

    def record_statement(
        self,
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        self.statements.append(statement)


def _build_file_id(sitting_date: date) -> str:
    return f"file-{sitting_date.isoformat()}"


def _build_file_url(sitting_date: date) -> str:
    return f"{settings.minutes_media_url}/{_build_file_id(sitting_date)}/VP.pdf"


@pytest.fixture
def fake_parliament(monkeypatch: pytest.MonkeyPatch) -> FakeParliament:
    fake_parliament = FakeParliament()
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
    return fake_parliament


@pytest.fixture(autouse=True)
def alerts(monkeypatch: pytest.MonkeyPatch) -> _AlertRecorder:
    alert_recorder = _AlertRecorder()
    monkeypatch.setattr(
        refresh_minutes, "send_telegram_message", alert_recorder.send_telegram_message
    )
    monkeypatch.setattr(settings, "telegram_bot_token", _BOT_TOKEN)
    monkeypatch.setattr(settings, "telegram_chat_id", _CHAT_ID)
    return alert_recorder


@pytest.fixture(autouse=True)
def engines(scratch_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(refresh_minutes, "engine", scratch_engine)
    monkeypatch.setattr(
        refresh_minutes,
        "build_read_only_engine",
        lambda database_url: scratch_engine.execution_options(postgresql_readonly=True),
    )


@pytest.fixture
def logged_messages() -> Iterator[list[str]]:
    messages: list[str] = []
    sink_id = logger.add(lambda message: messages.append(message.record["message"]))
    yield messages
    logger.remove(sink_id)


def _add_report(session: Session, sitting_date: date, report_id: str) -> None:
    add_division_report(
        session,
        report_id,
        datetime(sitting_date.year, sitting_date.month, sitting_date.day),
    )
    session.commit()


def _list_dates(fake_parliament: FakeParliament, listed_dates: list[date]) -> None:
    fake_parliament.minutes_index_page = build_live_index_page(
        [
            build_live_index_row(listed_date, 57, _build_file_id(listed_date), "VP.pdf")
            for listed_date in listed_dates
        ]
    )


def _answer_file(
    fake_parliament: FakeParliament, sitting_date: date, content: bytes
) -> None:
    file_url = _build_file_url(sitting_date)
    fake_parliament.file_url_to_response[file_url] = MinutesResponse(
        url=file_url, status_code=200, content=content
    )


def _seed_division_scenario(
    session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> Report:
    monkeypatch.setattr(
        minutes_step,
        "get_minutes_pdf_text",
        lambda content: _DIVISION_TEXT_FIXTURE.read_text(encoding="utf-8"),
    )
    seed_stored(session)
    report = add_division_report(session, "MINUTES-REPORT", datetime(2018, 1, 10))
    session.add(Minutes(sitting_date=_FIRST_DATE, status=MinutesStatus.NOT_YET_LISTED))
    session.commit()
    _list_dates(fake_parliament, [_FIRST_DATE])
    _answer_file(fake_parliament, _FIRST_DATE, _PDF_FIXTURE.read_bytes())
    return report


def _get_row_count(session: Session, table: type[SQLModel]) -> int:
    session.expire_all()
    return session.exec(select(func.count()).select_from(table)).one()


def _get_minutes(session: Session, sitting_date: date) -> Minutes:
    session.expire_all()
    return session.exec(
        select(Minutes).where(Minutes.sitting_date == sitting_date)
    ).one()


def _get_statement_effects(statement: str) -> list[tuple[str, str]]:
    verb_match = _STATEMENT_VERB_PATTERN.search(statement)
    if verb_match is None:
        return []
    verb = verb_match.group(1).upper()
    if verb == "UPDATE":
        update_match = _UPDATE_TABLE_PATTERN.search(statement)
        return [("UPDATE", "" if update_match is None else update_match.group(1))]
    if verb == "INSERT":
        insert_match = _INSERT_TABLE_PATTERN.search(statement)
        return [("INSERT", "" if insert_match is None else insert_match.group(1))]
    if verb == "SELECT":
        return [("SELECT", table) for table in _READ_TABLE_PATTERN.findall(statement)]
    return [(verb, "")]


def _get_statement_problems(statements: list[str]) -> list[str]:
    problems = []
    for statement in statements:
        if _STATEMENT_VERB_PATTERN.search(statement) is None:
            problems.append(f"No statement verb: {statement}")
            continue
        for effect in _get_statement_effects(statement):
            if effect not in _MINUTES_STEP_ALLOWED_STATEMENTS:
                problems.append(f"{effect[0]} {effect[1]} is not granted: {statement}")
        if _get_statement_effects(statement) != [("UPDATE", "minutes")]:
            continue
        set_match = _SET_CLAUSE_PATTERN.search(statement)
        if set_match is None:
            problems.append(f"UPDATE minutes has no WHERE: {statement}")
            continue
        problems.extend(
            f"Column {column} is not granted for UPDATE: {statement}"
            for column in _SET_COLUMN_PATTERN.findall(set_match.group(1))
            if column not in _MINUTES_STEP_UPDATE_COLUMNS
        )
    return problems


def test_dry_run_writes_nothing_fetches_nothing_and_sends_no_alert(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    logged_messages: list[str],
) -> None:
    _add_report(scratch_session, _FIRST_DATE, "R1")
    _add_report(scratch_session, _SECOND_DATE, "R2")
    _add_report(scratch_session, _THIRD_DATE, "R3")
    _list_dates(fake_parliament, [_FIRST_DATE, _SECOND_DATE])
    _answer_file(fake_parliament, _FIRST_DATE, _PDF_FIXTURE.read_bytes())

    refresh_minutes.refresh_minutes(_NOW, False)

    assert _get_row_count(scratch_session, Minutes) == 0
    assert _get_row_count(scratch_session, MinutesIndexCapture) == 0
    assert _get_row_count(scratch_session, RefreshRun) == 0
    assert fake_parliament.minutes_file_calls == []
    assert alerts.messages == []
    assert logged_messages[-1] == "Dry run: nothing written"
    assert "2 sittings listed, 2018-01-10 to 2018-01-11" in "\n".join(logged_messages)
    assert "New LISTED rows: 2018-01-10, 2018-01-11" in logged_messages
    assert "Rows moved to LISTED: none" in logged_messages
    assert "New NOT_YET_LISTED rows: 2018-01-12" in logged_messages
    assert "Files to fetch: 2018-01-10, 2018-01-11" in logged_messages


def test_dry_run_with_an_unreadable_index_page_raises_and_sends_no_alert(
    scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder
) -> None:
    fake_parliament.minutes_index_page = "<html><body></body></html>"

    with pytest.raises(HansardMinutesIndexError):
        refresh_minutes.refresh_minutes(_NOW, False)

    assert alerts.messages == []


def test_commit_run_stores_the_text_and_a_not_yet_listed_row_and_no_refresh_run(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_division_scenario(scratch_session, fake_parliament, monkeypatch)
    _add_report(scratch_session, _THIRD_DATE, "R3")

    refresh_minutes.refresh_minutes(_NOW, True)

    listed_minutes = _get_minutes(scratch_session, _FIRST_DATE)
    assert listed_minutes.status == MinutesStatus.TEXT_STORED
    assert listed_minutes.extracted_text is not None
    assert _get_minutes(scratch_session, _THIRD_DATE).status == (
        MinutesStatus.NOT_YET_LISTED
    )
    assert _get_row_count(scratch_session, MinutesIndexCapture) == 1
    assert _get_row_count(scratch_session, RefreshRun) == 0
    assert alerts.messages == []


def test_files_dated_inside_the_recheck_window_are_not_fetched(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    held_date = _TODAY - timedelta(days=_RECHECK_WINDOW_DAYS)
    fetched_date = held_date - timedelta(days=1)
    _add_report(scratch_session, held_date, "R1")
    _add_report(scratch_session, fetched_date, "R2")
    _list_dates(fake_parliament, [held_date, fetched_date])

    refresh_minutes.refresh_minutes(_NOW, True)

    assert fake_parliament.minutes_file_calls == [_build_file_url(fetched_date)]


def test_index_answer_of_202_sends_the_jobs_skip_text_and_raises_nothing(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        minutes_step,
        "get_minutes_index_response",
        lambda: MinutesResponse(
            url=settings.minutes_index_url,
            status_code=_ACCEPTED_STATUS,
            content=b"",
            waf_action="challenge",
            cache_status="Error from cloudfront",
        ),
    )

    refresh_minutes.refresh_minutes(_NOW, True)

    assert alerts.messages == [
        "Minutes index page not read: The minutes index page answered 202 "
        "(x-amzn-waf-action: challenge, x-cache: Error from cloudfront)"
        f"{_INDEX_SKIPPED_MESSAGE_END}"
    ]


def test_index_answer_of_404_sends_the_skip_alert_and_raises_nothing(
    scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder
) -> None:
    fake_parliament.minutes_index_status = _NOT_FOUND_STATUS

    refresh_minutes.refresh_minutes(_NOW, True)

    assert alerts.messages == [
        "Minutes index page not read: The minutes index page answered 404 "
        "(x-amzn-waf-action: None, x-cache: None)"
        f"{_INDEX_SKIPPED_MESSAGE_END}"
    ]


def test_index_network_failure_sends_the_skip_alert_and_raises_nothing(
    scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder
) -> None:
    fake_parliament.minutes_index_error = HansardGatewayError("index down")

    refresh_minutes.refresh_minutes(_NOW, True)

    assert alerts.messages == [
        f"Minutes index page not read: index down{_INDEX_SKIPPED_MESSAGE_END}"
    ]


def test_review_and_not_fetched_alerts_carry_the_jobs_texts_in_its_order(
    scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder
) -> None:
    _add_report(scratch_session, _SECOND_DATE, "R2")
    _add_report(scratch_session, _THIRD_DATE, "R3")
    _list_dates(fake_parliament, [_SECOND_DATE, _THIRD_DATE])
    _answer_file(fake_parliament, _SECOND_DATE, _PDF_FIXTURE.read_bytes())

    refresh_minutes.refresh_minutes(_NOW, True)

    assert alerts.messages == [
        "Minutes of 11 January 2018 need review: "
        "The file's head prints 10 January 2018, not the sitting date",
        "Minutes files listed but not fetched: 12 January 2018 (the request failed). "
        "Each stays LISTED and the next run tries it again.",
    ]


def test_a_row_listed_before_the_run_is_fetched_and_its_review_alerted(
    scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder
) -> None:
    _add_report(scratch_session, _SECOND_DATE, "R2")
    scratch_session.add(
        Minutes(
            sitting_date=_SECOND_DATE,
            status=MinutesStatus.LISTED,
            index_source=MinutesIndexSource.LIVE_PAGE,
            file_url=_build_file_url(_SECOND_DATE),
            file_format=MinutesFileFormat.PDF,
        )
    )
    scratch_session.commit()
    _list_dates(fake_parliament, [_SECOND_DATE])
    _answer_file(fake_parliament, _SECOND_DATE, _PDF_FIXTURE.read_bytes())

    refresh_minutes.refresh_minutes(_NOW, True)

    assert fake_parliament.minutes_file_calls == [_build_file_url(_SECOND_DATE)]
    assert alerts.messages == [
        "Minutes of 11 January 2018 need review: "
        "The file's head prints 10 January 2018, not the sitting date"
    ]


def test_unreadable_index_page_sends_the_failure_alert_and_raises(
    scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder
) -> None:
    fake_parliament.minutes_index_page = "<html><body></body></html>"

    with pytest.raises(HansardMinutesIndexError):
        refresh_minutes.refresh_minutes(_NOW, True)

    assert alerts.messages == [
        "Hansard minutes run failed. HansardMinutesIndexError: "
        "The live index page holds no initialMPs rows"
    ]


def test_a_non_hansard_error_alerts_its_type_only_and_propagates(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_with_a_host_name() -> MinutesResponse:
        raise RuntimeError("connection to db.example.test failed")

    monkeypatch.setattr(
        minutes_step, "get_minutes_index_response", fail_with_a_host_name
    )

    with pytest.raises(RuntimeError):
        refresh_minutes.refresh_minutes(_NOW, True)

    assert alerts.messages == ["Hansard minutes run failed. RuntimeError"]


@pytest.mark.parametrize("unset_setting", ["telegram_bot_token", "telegram_chat_id"])
def test_a_commit_run_refuses_while_a_telegram_setting_is_unset(
    unset_setting: str,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, unset_setting, None)
    _add_report(scratch_session, _FIRST_DATE, "R1")
    _list_dates(fake_parliament, [_FIRST_DATE])
    _answer_file(fake_parliament, _FIRST_DATE, _PDF_FIXTURE.read_bytes())

    with pytest.raises(HansardSettingError, match=unset_setting.upper()):
        refresh_minutes.refresh_minutes(_NOW, True)

    assert _get_row_count(scratch_session, Minutes) == 0
    assert _get_row_count(scratch_session, MinutesIndexCapture) == 0
    assert fake_parliament.minutes_file_calls == []
    assert alerts.messages == []


def test_a_dry_run_needs_no_telegram_setting(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    logged_messages: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "telegram_bot_token", None)
    monkeypatch.setattr(settings, "telegram_chat_id", None)
    _add_report(scratch_session, _FIRST_DATE, "R1")
    _list_dates(fake_parliament, [_FIRST_DATE])

    refresh_minutes.refresh_minutes(_NOW, False)

    assert "Files to fetch: 2018-01-10" in logged_messages
    assert logged_messages[-1] == "Dry run: nothing written"


def test_the_commit_run_statements_pass_the_grants_and_the_statement_check(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_division_scenario(scratch_session, fake_parliament, monkeypatch)
    recorder = _StatementRecorder()
    event.listen(scratch_engine, "before_cursor_execute", recorder.record_statement)
    try:
        refresh_minutes.refresh_minutes(_NOW, True)
    finally:
        event.remove(scratch_engine, "before_cursor_execute", recorder.record_statement)

    for statement_start in _MINUTES_WRITE_STATEMENT_STARTS:
        assert any(
            statement.startswith(statement_start) for statement in recorder.statements
        ), statement_start
    assert (
        get_grant_violations(
            recorder.statements,
            _TABLE_NAMES,
            get_role_grants(get_write_role_blocks()[0]),
        )
        == []
    )
    assert _get_statement_problems(recorder.statements) == []
    observed_effects = {
        effect
        for statement in recorder.statements
        for effect in _get_statement_effects(statement)
    }
    assert {
        ("INSERT", "minutes"),
        ("INSERT", "minutes_index_capture"),
        ("INSERT", "division"),
        ("INSERT", "minutes_division"),
        ("INSERT", "division_vote"),
        ("INSERT", "division_party_count"),
        ("UPDATE", "minutes"),
        ("SELECT", "report"),
        ("SELECT", "speaker"),
        ("SELECT", "division_party_count"),
    } <= observed_effects
    update_statements = [
        statement
        for statement in recorder.statements
        if _get_statement_effects(statement) == [("UPDATE", "minutes")]
    ]
    assert update_statements
    for update_statement in update_statements:
        set_match = _SET_CLAUSE_PATTERN.search(update_statement)
        assert set_match is not None
        assert _SET_COLUMN_PATTERN.findall(set_match.group(1))
    assert not {verb for verb, _ in observed_effects} & {"DELETE", "TRUNCATE", "GRANT"}


def test_statement_check_flags_an_update_of_a_column_outside_the_grant() -> None:
    problems = _get_statement_problems(
        ["UPDATE minutes SET status=%(status)s, id=%(id)s WHERE minutes.id = %(id_1)s"]
    )

    assert len(problems) == 1
    assert "Column id is not granted" in problems[0]


def test_statement_check_flags_an_update_of_another_table() -> None:
    problems = _get_statement_problems(
        ["UPDATE report SET title=%(title)s WHERE report.id = %(id_1)s"]
    )

    assert any("UPDATE report is not granted" in problem for problem in problems)


def test_statement_check_flags_an_update_without_a_where() -> None:
    problems = _get_statement_problems(["UPDATE minutes SET status=%(status)s"])

    assert any("has no WHERE" in problem for problem in problems)


def test_statement_check_passes_a_granted_update() -> None:
    assert _get_statement_problems([_GRANTED_UPDATE_STATEMENT]) == []


def test_the_commit_run_writes_divisions_in_the_file_commit(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_division_scenario(scratch_session, fake_parliament, monkeypatch)

    refresh_minutes.refresh_minutes(_NOW, True)

    assert _get_minutes(scratch_session, _FIRST_DATE).status == (
        MinutesStatus.TEXT_STORED
    )
    assert _get_row_count(scratch_session, MinutesDivision) == (
        _MINUTES_DIVISION_ROW_COUNT
    )


def test_the_commit_run_writes_the_breakdown_for_every_division_of_the_sitting(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _seed_division_scenario(scratch_session, fake_parliament, monkeypatch)
    hansard_only_division = Division(
        sitting_date=_FIRST_DATE,
        parliament_number=report.parliament_number,
        report_division_number=1,
        speech_ordinal=1,
        count_source=DivisionCountSource.PRINTED_LINE,
        printed_counts=_HANSARD_ONLY_PRINTED_COUNTS,
        ayes=1,
        noes=1,
        list_status=DivisionListStatus.STORED,
        sprs_report_id=report.report_id,
    )
    scratch_session.add(hansard_only_division)
    scratch_session.flush()
    assert hansard_only_division.id is not None
    hansard_only_division_id = hansard_only_division.id
    scratch_session.add(
        DivisionVote(
            ordinal=1,
            printed_name="Mr A",
            vote_choice=DivisionVoteChoice.AYE,
            list_source=DivisionVoteListSource.HANSARD,
            party="PAP",
            division_id=hansard_only_division_id,
        )
    )
    scratch_session.commit()

    refresh_minutes.refresh_minutes(_NOW, True)

    scratch_session.expire_all()
    division_ids_with_breakdown = set(
        scratch_session.exec(select(DivisionPartyCount.division_id)).all()
    )
    minutes_division_ids = set(
        scratch_session.exec(select(MinutesDivision.division_id)).all()
    )
    assert hansard_only_division_id in division_ids_with_breakdown
    assert len(minutes_division_ids) == _MINUTES_DIVISION_ROW_COUNT
    assert minutes_division_ids <= division_ids_with_breakdown


def test_a_failed_division_step_leaves_the_file_listed_with_no_rows_and_alerts(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_division_step(session: Session, minutes_id: int) -> None:
        raise HansardWriteCheckError("The division step failed")

    _seed_division_scenario(scratch_session, fake_parliament, monkeypatch)
    monkeypatch.setattr(minutes_step, "populate_minutes_divisions", fail_division_step)

    with pytest.raises(HansardWriteCheckError):
        refresh_minutes.refresh_minutes(_NOW, True)

    stored_minutes = _get_minutes(scratch_session, _FIRST_DATE)
    assert stored_minutes.status == MinutesStatus.LISTED
    assert stored_minutes.extracted_text is None
    assert _get_row_count(scratch_session, MinutesDivision) == 0
    assert alerts.messages == [
        "Hansard minutes run failed. HansardWriteCheckError: The division step failed"
    ]


def test_an_unreadable_division_file_is_needs_review_with_no_division_rows(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        minutes_step, "get_minutes_pdf_text", lambda content: _UNREADABLE_DIVISION_TEXT
    )
    seed_stored(scratch_session)
    _add_report(scratch_session, _SECOND_DATE, "MINUTES-REPORT")
    _list_dates(fake_parliament, [_SECOND_DATE])
    _answer_file(fake_parliament, _SECOND_DATE, _PDF_FIXTURE.read_bytes())

    refresh_minutes.refresh_minutes(_NOW, True)

    stored_minutes = _get_minutes(scratch_session, _SECOND_DATE)
    assert stored_minutes.status == MinutesStatus.NEEDS_REVIEW
    assert stored_minutes.status_note == UNREAD_DIVISION_STATUS_NOTE
    assert _get_row_count(scratch_session, MinutesDivision) == 0
    assert alerts.messages == [
        f"Minutes of 11 January 2018 need review: {UNREAD_DIVISION_STATUS_NOTE}"
    ]
