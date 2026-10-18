import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, func, select

import populate.refresh_runs as refresh_runs
from crud.attendance import CRUDAttendance
from crud.refresh_run import CRUDRefreshRun
from crud.speech import CRUDSpeech
from database.attendance import Attendance
from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.hansard_website_response import HansardWebsiteResponse
from database.party_affiliation import PartyAffiliation
from database.person import Person
from database.refresh_run import RefreshRun
from database.report import Report
from database.sitting import Sitting
from database.speaker import Speaker
from database.speech import Speech
from enums import RefreshRunStatus
from exceptions import HansardGatewayError, HansardRefreshRunError
from schemas.hansard_report_response import HansardReportNewResponse
from schemas.hansard_topic_response import HansardTopicResponse
from services.refresh import SINGAPORE_TIMEZONE, get_sitting_date_key
from settings import settings
from tests.refresh_fixtures import FakeParliament, load_speaker_rows, seed_stored

_BOT_TOKEN = "test-bot-token"
_CHAT_ID = "test-chat"
_PING_URL = "https://hc-ping.test/test-check"
_DATABASE_ERROR = "connection to server at db.example failed"
_DATABASE_HOST = "db.example"
_NEW_PARLIAMENT_NUMBER = 15
_OTHER_PARLIAMENT_NUMBER = 16
_UNREGISTERED_LABEL = "Mr Nobody Registered"
_FRESH_RUN_AGE = timedelta(hours=1)
_STALE_RUN_AGE = timedelta(hours=13)
_DAYS_AFTER_NEW_SITTING = 2
_SINGAPORE_RUN_HOUR = 4
_RECHECK_WINDOW_DAYS = 14
_HELD_ALERT_DAY_OFFSET = 1
_MAX_NAMED_UNLINKED_ROWS = 1
_SUMMARY_RE = re.compile(r"^\d+ sittings?, \d+ reports?, [\d,]+ rows?, \d+\.\d% linked$")
_STRONG_LABEL_RE = re.compile(r"<strong>((?:Mr|Ms|Mrs|Dr) [^<:]+)</strong>")
_FIRST_WORD_RE = re.compile(r"\bthe\b")
_DATA_TABLES = (
    HansardWebsiteResponse,
    Report,
    Speech,
    HansardSittingDateResponse,
    Sitting,
    Attendance,
    Speaker,
    Person,
    PartyAffiliation,
)
_GROWING_TABLES = (HansardWebsiteResponse, Report, Speech, HansardSittingDateResponse, Sitting, Attendance)
_ADDED_COUNT_COLUMNS = (
    "website_responses_added",
    "sitting_date_responses_added",
    "sittings_added",
    "reports_added",
    "speeches_added",
    "attendances_added",
)


@dataclass
class _AlertRecorder:
    messages: list[str] = field(default_factory=list)
    pings: list[str] = field(default_factory=list)

    def send_telegram_message(self, bot_token: str, chat_id: str, text: str) -> None:
        self.messages.append(text)

    def send_healthchecks_ping(self, ping_url: str) -> None:
        self.pings.append(ping_url)


@pytest.fixture(autouse=True)
def fake_parliament(monkeypatch: pytest.MonkeyPatch) -> FakeParliament:
    fake_parliament = FakeParliament()
    monkeypatch.setattr(refresh_runs, "get_all_hansard_search_results", fake_parliament.get_all_hansard_search_results)
    monkeypatch.setattr(refresh_runs, "get_hansard_report_response", fake_parliament.get_hansard_report_response)
    monkeypatch.setattr(refresh_runs, "get_hansard_topic_response_async", fake_parliament.get_hansard_topic_response_async)
    return fake_parliament


@pytest.fixture(autouse=True)
def alerts(monkeypatch: pytest.MonkeyPatch) -> _AlertRecorder:
    alert_recorder = _AlertRecorder()
    monkeypatch.setattr(refresh_runs, "send_telegram_message", alert_recorder.send_telegram_message)
    monkeypatch.setattr(refresh_runs, "send_healthchecks_ping", alert_recorder.send_healthchecks_ping)
    monkeypatch.setattr(settings, "telegram_bot_token", _BOT_TOKEN)
    monkeypatch.setattr(settings, "telegram_chat_id", _CHAT_ID)
    monkeypatch.setattr(settings, "healthchecks_ping_url", _PING_URL)
    return alert_recorder


def _get_now(fake_parliament: FakeParliament, days_after_new_sitting: int = _DAYS_AFTER_NEW_SITTING) -> datetime:
    run_date = fake_parliament.new_sitting_date + timedelta(days=days_after_new_sitting)
    return datetime(run_date.year, run_date.month, run_date.day, _SINGAPORE_RUN_HOUR, tzinfo=SINGAPORE_TIMEZONE).astimezone(timezone.utc)


def _get_row_counts(scratch_engine: Engine) -> dict[str, int]:
    with Session(scratch_engine) as session:
        return {
            table.__name__: session.exec(select(func.count()).select_from(table)).one()
            for table in _DATA_TABLES
        }


def _get_refresh_runs(scratch_engine: Engine) -> list[RefreshRun]:
    with Session(scratch_engine) as session:
        return list(session.exec(select(RefreshRun).order_by(col(RefreshRun.id))).all())


def _get_only_refresh_run(scratch_engine: Engine) -> RefreshRun:
    refresh_runs_stored = _get_refresh_runs(scratch_engine)
    assert len(refresh_runs_stored) == 1
    return refresh_runs_stored[0]


def _set_new_parliament_number(fake_parliament: FakeParliament, parliament_number: int) -> None:
    for search_result in fake_parliament.new_search_results:
        search_result["parlNo"] = str(parliament_number)
    fake_parliament.new_sitting["metadata"]["parlimentNO"] = parliament_number


def _get_first_new_report_id(fake_parliament: FakeParliament) -> str:
    return fake_parliament.new_search_results[0]["reportId"]


def _get_new_contents(fake_parliament: FakeParliament) -> list[str]:
    return [
        fake_parliament.report_id_to_topic[search_result["reportId"]]["resultHTML"]["content"]
        for search_result in fake_parliament.new_search_results
    ]


def _assert_nothing_written(scratch_engine: Engine, row_counts_before: dict[str, int]) -> None:
    assert _get_row_counts(scratch_engine) == row_counts_before


def _assert_halted(scratch_engine: Engine, alerts: _AlertRecorder, row_counts_before: dict[str, int]) -> RefreshRun:
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.HALTED
    assert refresh_run.halt_reason is not None
    assert refresh_run.failure_reason is None
    assert all(getattr(refresh_run, column) == 0 for column in _ADDED_COUNT_COLUMNS)
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh halted.")
    assert alerts.pings == [_PING_URL]
    return refresh_run


def _assert_failed(scratch_engine: Engine, alerts: _AlertRecorder, row_counts_before: dict[str, int], error_name: str) -> RefreshRun:
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.FAILED
    assert refresh_run.failure_reason is not None
    assert refresh_run.failure_reason.startswith(error_name)
    assert refresh_run.finished_at is not None
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh failed.")
    assert error_name in alerts.messages[0]
    assert alerts.pings == [_PING_URL]
    return refresh_run


def _assert_rows_added(scratch_engine: Engine, row_counts_before: dict[str, int], refresh_run: RefreshRun) -> None:
    row_counts_after = _get_row_counts(scratch_engine)
    assert row_counts_after["HansardWebsiteResponse"] - row_counts_before["HansardWebsiteResponse"] == refresh_run.website_responses_added
    assert row_counts_after["Report"] - row_counts_before["Report"] == refresh_run.reports_added
    assert row_counts_after["Speech"] - row_counts_before["Speech"] == refresh_run.speeches_added
    assert row_counts_after["Sitting"] - row_counts_before["Sitting"] == refresh_run.sittings_added
    assert row_counts_after["Attendance"] - row_counts_before["Attendance"] == refresh_run.attendances_added


def _raise_database_error(*args: object) -> None:
    raise SQLAlchemyError(_DATABASE_ERROR)


def test_clean_run_adds_rows_and_links_them(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.SUCCEEDED
    row_counts_after = _get_row_counts(scratch_engine)
    for table in _DATA_TABLES:
        if table in _GROWING_TABLES:
            assert row_counts_after[table.__name__] > row_counts_before[table.__name__]
            continue
        assert row_counts_after[table.__name__] == row_counts_before[table.__name__]
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.SUCCEEDED
    assert refresh_run.speeches_linked > 0
    assert refresh_run.speeches_named_unlinked <= _MAX_NAMED_UNLINKED_ROWS
    assert refresh_run.reports_added == len(fake_parliament.new_search_results)
    assert refresh_run.latest_sitting_date_with_text == fake_parliament.new_sitting_date
    assert refresh_run.figures is not None
    groups = refresh_run.figures["groups"]
    assert isinstance(groups, list)
    parliament_group = next(group for group in groups if group["group"] == "Parliament 14")
    assert "zero_row_report_count" in parliament_group
    assert parliament_group["report_types"] != []
    assert len([message for message in alerts.messages if _SUMMARY_RE.match(message)]) == 1
    assert alerts.pings == [_PING_URL]
    with Session(scratch_engine) as session:
        new_sitting = session.exec(
            select(Sitting).where(Sitting.sitting_date == get_sitting_date_key(fake_parliament.new_sitting_date))
        ).one()
        assert new_sitting.id is not None
        assert new_sitting.sections is not None
        assert refresh_run.attendances_linked > 0
        assert refresh_run.attendances_linked == CRUDAttendance(session).get_count_by_sitting_ids_and_speaker_id_not_null([new_sitting.id])
        new_report_ids = {search_result["reportId"] for search_result in fake_parliament.new_search_results}
        speech_report_rows = session.exec(
            select(Speech.sitting_date, Report.sitting_date)
            .join(Report, col(Speech.report_id) == col(Report.id))
            .where(col(Report.report_id).in_(new_report_ids))
        ).all()
        assert speech_report_rows != []
        for speech_sitting_date, report_sitting_date in speech_report_rows:
            assert speech_sitting_date == report_sitting_date
        stored_report_ids = [
            report.id for report in session.exec(select(Report).where(col(Report.report_id).not_in(new_report_ids))).all()
            if report.id is not None
        ]
        assert all(speech_row.speaker_id is None for speech_row in CRUDSpeech(session).get_rows_by_report_ids(stored_report_ids))
        stored_sitting = session.exec(
            select(Sitting).where(Sitting.sitting_date == get_sitting_date_key(fake_parliament.stored_sitting_date))
        ).one()
        assert stored_sitting.id is not None
        assert CRUDAttendance(session).get_count_by_sitting_ids_and_speaker_id_not_null([stored_sitting.id]) == 0


def test_run_that_adds_nothing_sends_no_message(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)
    row_counts_before = _get_row_counts(scratch_engine)
    alerts.messages.clear()
    alerts.pings.clear()

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.SUCCEEDED
    second_run = _get_refresh_runs(scratch_engine)[-1]
    assert second_run.status == RefreshRunStatus.SUCCEEDED
    assert all(getattr(second_run, column) == 0 for column in _ADDED_COUNT_COLUMNS)
    assert second_run.figures is None
    assert second_run.reports_changed == 0
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert alerts.messages == []
    assert alerts.pings == [_PING_URL]


def test_new_parliament_number_halts(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _set_new_parliament_number(fake_parliament, _NEW_PARLIAMENT_NUMBER)

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert str(_NEW_PARLIAMENT_NUMBER) in refresh_run.halt_reason
    assert fake_parliament.topic_calls == []
    assert fake_parliament.sitting_calls == []


def test_new_parliament_number_in_sitting_body_halts(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    fake_parliament.new_sitting["metadata"]["parlimentNO"] = _NEW_PARLIAMENT_NUMBER

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert str(_NEW_PARLIAMENT_NUMBER) in refresh_run.halt_reason
    assert fake_parliament.topic_calls != []


def test_allowed_parliament_number_runs(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    scratch_session.add_all([
        Speaker(**{**speaker_row, "parliament_number": _NEW_PARLIAMENT_NUMBER}) for speaker_row in load_speaker_rows()
    ])
    scratch_session.commit()
    _set_new_parliament_number(fake_parliament, _NEW_PARLIAMENT_NUMBER)
    row_counts_before = _get_row_counts(scratch_engine)

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), _NEW_PARLIAMENT_NUMBER)

    assert status == RefreshRunStatus.SUCCEEDED
    refresh_run = _get_only_refresh_run(scratch_engine)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    assert refresh_run.status == RefreshRunStatus.SUCCEEDED
    assert refresh_run.reports_added == len(fake_parliament.new_search_results)
    assert len([message for message in alerts.messages if _SUMMARY_RE.match(message)]) == 1
    assert alerts.pings == [_PING_URL]


def test_other_parliament_number_halts_when_one_is_allowed(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _set_new_parliament_number(fake_parliament, _OTHER_PARLIAMENT_NUMBER)

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), _NEW_PARLIAMENT_NUMBER)

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert str(_OTHER_PARLIAMENT_NUMBER) in refresh_run.halt_reason


def test_field_mapping_failure_halts(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    report_id = _get_first_new_report_id(fake_parliament)
    content = fake_parliament.report_id_to_topic[report_id]["resultHTML"]["content"]
    fake_parliament.report_id_to_topic[report_id] = {"htmlContent": content}

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert "field mapping check" in refresh_run.halt_reason


def test_sitting_field_mapping_failure_halts(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    assert fake_parliament.new_sitting["metadata"]["sessionNO"] not in (None, "")
    build_new_hansard_sitting_date_response = refresh_runs.build_new_hansard_sitting_date_response

    def build_lossy_sitting_date_response(hansard_report_response: HansardReportNewResponse, sitting_date: str) -> HansardSittingDateResponse:
        hansard_sitting_date_response = build_new_hansard_sitting_date_response(hansard_report_response, sitting_date)
        hansard_sitting_date_response.session_no = None
        return hansard_sitting_date_response

    monkeypatch.setattr(refresh_runs, "build_new_hansard_sitting_date_response", build_lossy_sitting_date_response)

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert "sessionNO" in refresh_run.halt_reason


def test_unlinked_share_over_limit_halts(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    new_contents = _get_new_contents(fake_parliament)
    speaker_names_to_drop = frozenset(
        speaker_row["name"] for speaker_row in load_speaker_rows() if any(speaker_row["name"] in content for content in new_contents)
    )
    seed_stored(scratch_session, speaker_names_to_drop)
    row_counts_before = _get_row_counts(scratch_engine)

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert "% of new speech rows" in refresh_run.halt_reason
    assert any(speaker_name in refresh_run.halt_reason for speaker_name in speaker_names_to_drop)
    assert any(speaker_name in alerts.messages[0] for speaker_name in speaker_names_to_drop)


def test_missing_member_is_stored_unlinked(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    report_id, match = next(
        (search_result["reportId"], match)
        for search_result in fake_parliament.new_search_results
        if (match := _STRONG_LABEL_RE.search(fake_parliament.report_id_to_topic[search_result["reportId"]]["resultHTML"]["content"])) is not None
    )
    topic = fake_parliament.report_id_to_topic[report_id]["resultHTML"]
    topic["content"] = topic["content"].replace(match.group(0), f"<strong>{_UNREGISTERED_LABEL}</strong>", 1)

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.SUCCEEDED
    refresh_run = _get_only_refresh_run(scratch_engine)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    assert refresh_run.status == RefreshRunStatus.SUCCEEDED
    with Session(scratch_engine) as session:
        unregistered_speeches = session.exec(select(Speech).where(Speech.speaker == _UNREGISTERED_LABEL)).all()
    assert unregistered_speeches != []
    assert all(speech.speaker_id is None for speech in unregistered_speeches)
    assert any(message.startswith("Speaker labels with no registry match") and _UNREGISTERED_LABEL in message for message in alerts.messages)
    assert alerts.pings == [_PING_URL]


def test_changed_report_in_window_alerts_and_keeps_text(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    stored_report_id = fake_parliament.stored_search_results[0]["reportId"]
    with Session(scratch_engine) as session:
        stored_content = session.exec(
            select(HansardWebsiteResponse.content).where(HansardWebsiteResponse.report_id == stored_report_id)
        ).one()
        stored_markdown = session.exec(select(Report.markdown_content).where(Report.report_id == stored_report_id)).one()
    assert stored_content is not None
    assert _FIRST_WORD_RE.search(stored_content) is not None
    fake_parliament.report_id_to_topic[stored_report_id] = {"resultHTML": {"content": _FIRST_WORD_RE.sub("a", stored_content, count=1)}}

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.SUCCEEDED
    refresh_run = _get_only_refresh_run(scratch_engine)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    assert refresh_run.reports_changed == 1
    assert refresh_run.reports_rechecked == len(fake_parliament.stored_search_results)
    assert any(message.startswith(f"Report {stored_report_id} of") and "changed on SPRS" in message for message in alerts.messages)
    with Session(scratch_engine) as session:
        assert session.exec(
            select(HansardWebsiteResponse.content).where(HansardWebsiteResponse.report_id == stored_report_id)
        ).one() == stored_content
        assert session.exec(select(Report.markdown_content).where(Report.report_id == stored_report_id)).one() == stored_markdown
    assert alerts.pings == [_PING_URL]


def test_report_without_text_is_held(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    held_report_id = _get_first_new_report_id(fake_parliament)
    fake_parliament.report_id_to_topic[held_report_id] = {"resultHTML": {"content": None}}

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.SUCCEEDED
    refresh_run = _get_only_refresh_run(scratch_engine)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    assert refresh_run.reports_held_without_text == 1
    assert refresh_run.reports_added == len(fake_parliament.new_search_results) - 1
    with Session(scratch_engine) as session:
        assert session.exec(select(HansardWebsiteResponse).where(HansardWebsiteResponse.report_id == held_report_id)).all() == []
    assert not any("still has no text" in message for message in alerts.messages)
    assert alerts.pings == [_PING_URL]
    alerts.messages.clear()
    alerts.pings.clear()

    second_day_now = _get_now(fake_parliament, _RECHECK_WINDOW_DAYS + _HELD_ALERT_DAY_OFFSET - 1)
    status = refresh_runs.populate_refresh_runs(scratch_session, second_day_now, None)

    assert status == RefreshRunStatus.SUCCEEDED
    assert _get_refresh_runs(scratch_engine)[-1].reports_held_without_text == 1
    assert any(message.startswith(f"Report {held_report_id} of") and "still has no text" in message for message in alerts.messages)
    assert alerts.pings == [_PING_URL]


def test_gateway_failure_fails_the_run(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)

    async def raise_gateway_error(topic_id: str, client: httpx.AsyncClient) -> HansardTopicResponse:
        raise HansardGatewayError(f"Topic request failed for {topic_id}")

    monkeypatch.setattr(refresh_runs, "get_hansard_topic_response_async", raise_gateway_error)

    with pytest.raises(HansardGatewayError):
        refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    refresh_run = _assert_failed(scratch_engine, alerts, row_counts_before, "HansardGatewayError")
    assert refresh_run.failure_reason is not None
    assert "Topic request failed" in refresh_run.failure_reason


def test_database_error_mid_write_fails_the_run(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    monkeypatch.setattr(CRUDSpeech, "add_many", _raise_database_error)

    with pytest.raises(SQLAlchemyError):
        refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    _assert_failed(scratch_engine, alerts, row_counts_before, "SQLAlchemyError")
    assert _DATABASE_HOST not in alerts.messages[0]


def test_failure_at_start_still_alerts_and_pings(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    monkeypatch.setattr(CRUDRefreshRun, "create", _raise_database_error)

    with pytest.raises(SQLAlchemyError):
        refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert _get_refresh_runs(scratch_engine) == []
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh failed.")
    assert "SQLAlchemyError" in alerts.messages[0]
    assert _DATABASE_HOST not in alerts.messages[0]
    assert alerts.pings == [_PING_URL]


def test_finish_guard_error_in_halt_still_alerts_and_pings(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _set_new_parliament_number(fake_parliament, _NEW_PARLIAMENT_NUMBER)

    def mark_running_run_failed() -> None:
        with Session(scratch_engine) as session:
            running_run = session.exec(select(RefreshRun).where(RefreshRun.status == RefreshRunStatus.RUNNING)).one()
            running_run.status = RefreshRunStatus.FAILED
            session.add(running_run)
            session.commit()

    fake_parliament.on_search = mark_running_run_failed

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.HALTED
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.FAILED
    assert refresh_run.halt_reason is None
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh halted.")
    assert alerts.pings == [_PING_URL]


def test_finish_database_error_in_halt_still_alerts_and_pings(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _set_new_parliament_number(fake_parliament, _NEW_PARLIAMENT_NUMBER)
    monkeypatch.setattr(CRUDRefreshRun, "get_by_id_for_update", _raise_database_error)

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.HALTED
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.RUNNING
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh halted.")
    assert _DATABASE_HOST not in alerts.messages[0]
    assert alerts.pings == [_PING_URL]


def test_unset_alert_settings_send_nothing(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder, monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    monkeypatch.setattr(settings, "telegram_bot_token", None)
    monkeypatch.setattr(settings, "telegram_chat_id", None)
    monkeypatch.setattr(settings, "healthchecks_ping_url", None)

    status = refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert status == RefreshRunStatus.SUCCEEDED
    assert _get_only_refresh_run(scratch_engine).status == RefreshRunStatus.SUCCEEDED
    _assert_rows_added(scratch_engine, row_counts_before, _get_only_refresh_run(scratch_engine))
    assert alerts.messages == []
    assert alerts.pings == []


def _seed_running_run(scratch_session: Session, started_at: datetime) -> int:
    refresh_run = RefreshRun(started_at=started_at)
    scratch_session.add(refresh_run)
    scratch_session.commit()
    assert refresh_run.id is not None
    return refresh_run.id


def _get_refresh_run(scratch_engine: Engine, refresh_run_id: int) -> Optional[RefreshRun]:
    with Session(scratch_engine) as session:
        return session.get(RefreshRun, refresh_run_id)


def test_fresh_running_row_blocks_a_second_run(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    now = _get_now(fake_parliament)
    running_run_id = _seed_running_run(scratch_session, now - _FRESH_RUN_AGE)

    with pytest.raises(HansardRefreshRunError):
        refresh_runs.populate_refresh_runs(scratch_session, now, None)

    running_run, new_run = _get_refresh_runs(scratch_engine)
    assert running_run.id == running_run_id
    assert running_run.status == RefreshRunStatus.RUNNING
    assert new_run.status == RefreshRunStatus.FAILED
    assert new_run.failure_reason is not None
    assert "Another run is in progress" in new_run.failure_reason
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh failed.")
    assert alerts.pings == [_PING_URL]


def test_stale_running_row_is_marked_failed(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    now = _get_now(fake_parliament)
    stale_run_id = _seed_running_run(scratch_session, now - _STALE_RUN_AGE)
    row_counts_before = _get_row_counts(scratch_engine)

    status = refresh_runs.populate_refresh_runs(scratch_session, now, None)

    assert status == RefreshRunStatus.SUCCEEDED
    stale_run = _get_refresh_run(scratch_engine, stale_run_id)
    assert stale_run is not None
    assert stale_run.status == RefreshRunStatus.FAILED
    assert stale_run.failure_reason == "Run ended without finishing"
    assert _get_refresh_runs(scratch_engine)[-1].status == RefreshRunStatus.SUCCEEDED
    _assert_rows_added(scratch_engine, row_counts_before, _get_refresh_runs(scratch_engine)[-1])
    assert len([message for message in alerts.messages if _SUMMARY_RE.match(message)]) == 1
    assert alerts.pings == [_PING_URL]

