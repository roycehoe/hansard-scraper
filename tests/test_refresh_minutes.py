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
from database.minutes import Minutes, MinutesIndexCapture
from database.refresh_run import RefreshRun
from enums import MinutesStatus
from exceptions import HansardGatewayError, HansardMinutesIndexError
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


@pytest.fixture
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
) -> None:
    monkeypatch.setattr(
        minutes_step,
        "get_minutes_pdf_text",
        lambda content: _DIVISION_TEXT_FIXTURE.read_text(encoding="utf-8"),
    )
    seed_stored(session)
    add_division_report(session, "MINUTES-REPORT", datetime(2018, 1, 10))
    session.add(Minutes(sitting_date=_FIRST_DATE, status=MinutesStatus.NOT_YET_LISTED))
    session.commit()
    _list_dates(fake_parliament, [_FIRST_DATE])
    _answer_file(fake_parliament, _FIRST_DATE, _PDF_FIXTURE.read_bytes())


def _get_row_count(session: Session, table: type[SQLModel]) -> int:
    session.expire_all()
    return session.exec(select(func.count()).select_from(table)).one()


def _get_minutes(session: Session, sitting_date: date) -> Minutes:
    session.expire_all()
    return session.exec(
        select(Minutes).where(Minutes.sitting_date == sitting_date)
    ).one()


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
def test_a_missing_telegram_setting_sends_nothing(
    unset_setting: str,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, unset_setting, None)
    fake_parliament.minutes_index_error = HansardGatewayError("index down")

    refresh_minutes.refresh_minutes(_NOW, True)

    assert alerts.messages == []


def test_the_commit_run_statements_pass_the_grants_in_the_doc(
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
