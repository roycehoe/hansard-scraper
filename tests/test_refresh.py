import copy
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

import httpx
import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, col, func, select

import populate.minutes as minutes_step
import populate.refresh_runs as refresh_runs
import services.hansard_sitting_date_response as hansard_sitting_date_response_service
from crud.attendance import CRUDAttendance
from crud.refresh_run import CRUDRefreshRun
from crud.report import CRUDReport
from crud.speech import CRUDSpeech
from database.attached_file import AttachedFile
from database.attached_file_pointer import AttachedFilePointer
from database.attendance import Attendance
from database.attendance_office import AttendanceOffice
from database.division import Division
from database.division_party_count import DivisionPartyCount
from database.division_vote import DivisionVote
from database.hansard_sitting_date_response import HansardSittingDateResponse
from database.hansard_website_response import HansardWebsiteResponse
from database.leave_period import LeavePeriod, LeavePeriodPrinting
from database.ministry import Ministry
from database.minutes import Minutes
from database.minutes_division import MinutesDivision
from database.office_printed_range import OfficePrintedRange
from database.office_title_ministry import OfficeTitleMinistry
from database.party_affiliation import PartyAffiliation
from database.person import Person
from database.refresh_run import RefreshRun
from database.report import Report
from database.report_asker import ReportAsker
from database.report_participant import ReportParticipant
from database.report_put_to import ReportPutTo
from database.seat_holding import SeatHolding
from database.sitting import Sitting
from database.speaker import Speaker
from database.speech import Speech
from enums import (
    AttachedFileKind,
    AttachedFilePointerShape,
    AttendanceOfficeSource,
    DivisionCountSource,
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteListSource,
    MinutesFileFormat,
    MinutesIndexSource,
    MinutesStatus,
    OfficeClass,
    ParticipantRole,
    RefreshRunStatus,
    ReportType,
)
from exceptions import (
    HansardError,
    HansardGatewayError,
    HansardMinutesIndexError,
    HansardRefreshFailureError,
    HansardRefreshRunError,
    HansardWriteCheckError,
)
from populate.minutes import MinutesStepResult
from populate.minutes_divisions import UNREAD_DIVISION_STATUS_NOTE
from populate.report_askers import REPORT_ASKER_REPORT_TYPES
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from schemas.hansard_search_result import HansardSearchResult
from schemas.hansard_topic_response import HansardTopicResponse
from schemas.minutes_response import MinutesResponse
from services.hansard_website import get_topic_id
from services.refresh import (
    MAX_NEW_HITS_WITHOUT_TEXT,
    SINGAPORE_TIMEZONE,
    build_stale_report_links_message,
    get_dates_between,
)
from settings import settings
from tests.division_seed import add_division_report
from tests.refresh_fixtures import (
    FakeParliament,
    build_live_index_page,
    build_live_index_row,
    load_speaker_rows,
    seed_stored,
)
from utils.data_files import get_ministry_names
from utils.sitting_dates import get_sitting_date_key, parse_sitting_date

_MINUTES_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures" / "minutes"
_MINUTES_PDF_FIXTURE = "vp-10jan18-first-pages.pdf"
_MINUTES_DIVISION_TEXT_FIXTURE = (
    Path(__file__).parent / "division_fixtures" / "minutes_2021_10_04.txt"
)
_UNREADABLE_DIVISION_TEXT = "On Question put, the House divided."
_MINUTES_DIVISION_ROW_COUNT = 2
_HANSARD_ONLY_PRINTED_COUNTS = "The House divided: Ayes, 1; Noes, 1."
_MINUTES_FILE_ID = "minutes-file-id"
_MINUTES_FILE_NAME = "VP-11Jan2018.pdf"
_MINUTES_FILE_NUMBER = 57
_MINUTES_ALERT_FRAGMENT = "Minutes of 11 January 2018 need review"
_MINUTES_NOT_FETCHED_ALERT_FRAGMENT = "Minutes files listed but not fetched"
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
_NOT_FOUND_STATUS = 404
_BOT_TOKEN = "test-bot-token"
_CHAT_ID = "test-chat"
_PING_URL = "https://hc-ping.test/test-check"
_DATABASE_ERROR = "connection to server at db.example failed"
_DATABASE_HOST = "db.example"
_NEW_PARLIAMENT_NUMBER = 15
_OTHER_PARLIAMENT_NUMBER = 16
_PREVIOUS_PARLIAMENT_NUMBER = 14
_UNREGISTERED_LABEL = "Mr Nobody Registered"
_ATTACHED_FILE_ADDRESS = "20240910/annex-Refresh Test.pdf"
_STORED_REPORT_ID = "motion-2475#"
_ATTACHED_FILE_ID = 9001
_FIXTURE_FILE_COUNT = 9
_FRESH_RUN_AGE = timedelta(hours=1)
_STALE_RUN_AGE = timedelta(hours=13)
_DAYS_AFTER_NEW_SITTING = 2
_SINGAPORE_RUN_HOUR = 4
_RECHECK_WINDOW_DAYS = 14
_HELD_ALERT_DAY_OFFSET = 1
_MAX_NAMED_UNLINKED_ROWS = 1
_OCTOBER_RUN_DATE = date(2024, 10, 1)
_OCTOBER_SITTING_DATE_KEY = "1-10-2024"
_OCTOBER_REPORT_ID = "written-answer-na-99999#"
_OCTOBER_MONTH = 10
_LEAVE_MEMBER_NAME = "Mr Chee Hong Tat"
_NEW_SITTING_DATE_KEY = "10-9-2024"
_LEAVE_MEMBER_SPEAKER_NAME = "Chee Hong Tat"
_LEAVE_MEMBER_OFFICE = "Minister for Transport and Second Minister for Finance"
_LEAVE_MEMBER_DIVISION = "Bishan-Toa Payoh"
_LEAVE_MEMBER_DIVISION_KEY = "bishan toa payoh"
_EARLIER_SEAT_DATE = date(2024, 1, 1)
_SEAT_UPDATE_COLUMNS = (
    "first_sitting_date",
    "last_sitting_date",
    "sitting_count",
)
_UNREAD_REPORT_ID = 123
_UNREAD_DIVISION_ALERT_FRAGMENT = "new reports hold a division opening"
_RESUMED_PROBE_START_DATE = date(2024, 9, 11)
_STRONG_TEXT_RE = re.compile(r"<strong>[^<]+</strong>")
_SUMMARY_RE = re.compile(
    r"^\d+ sittings?, \d+ reports?, [\d,]+ rows?, \d+\.\d% linked$"
)
_STRONG_LABEL_RE = re.compile(r"<strong>((?:Mr|Ms|Mrs|Dr) [^<:]+)</strong>")
_FIRST_WORD_RE = re.compile(r"\bthe\b")
_LATE_SITTING_MEMBER = "Late Seed Member"
_LATE_SITTING_ENTRY_LINE = (
    "Mr Late Seed Member (Bishan-Toa Payoh), Minister for Health."
)
_UNPLACED_TITLE = "Minister for Nonsense"
_UNPLACED_ENTRY_LINE = "Mr Chee Hong Tat (Bishan-Toa Payoh), Minister for Nonsense."
_MISSING_TABLE_VACUUM = "VACUUM (ANALYZE) no_such_table"
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
_GROWING_TABLES = (
    HansardWebsiteResponse,
    Report,
    Speech,
    HansardSittingDateResponse,
    Sitting,
    Attendance,
)
_OFFICE_TABLES = (
    AttendanceOffice,
    OfficePrintedRange,
    ReportPutTo,
    OfficeTitleMinistry,
)
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
    failure_pings: list[str] = field(default_factory=list)

    def send_telegram_message(self, bot_token: str, chat_id: str, text: str) -> None:
        self.messages.append(text)

    def send_healthchecks_ping(self, ping_url: str) -> None:
        self.pings.append(ping_url)

    def send_healthchecks_failure_ping(self, ping_url: str) -> None:
        self.failure_pings.append(ping_url)


@pytest.fixture(autouse=True)
def _no_report_link_title_corrections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("populate.report_links.get_report_link_title_corrections", list)


@pytest.fixture(autouse=True)
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
    return fake_parliament


@pytest.fixture(autouse=True)
def alerts(monkeypatch: pytest.MonkeyPatch) -> _AlertRecorder:
    alert_recorder = _AlertRecorder()
    monkeypatch.setattr(
        refresh_runs, "send_telegram_message", alert_recorder.send_telegram_message
    )
    monkeypatch.setattr(
        refresh_runs, "send_healthchecks_ping", alert_recorder.send_healthchecks_ping
    )
    monkeypatch.setattr(
        refresh_runs,
        "send_healthchecks_failure_ping",
        alert_recorder.send_healthchecks_failure_ping,
    )
    monkeypatch.setattr(settings, "telegram_bot_token", _BOT_TOKEN)
    monkeypatch.setattr(settings, "telegram_chat_id", _CHAT_ID)
    monkeypatch.setattr(settings, "healthchecks_ping_url", _PING_URL)
    return alert_recorder


def _get_now(
    fake_parliament: FakeParliament,
    days_after_new_sitting: int = _DAYS_AFTER_NEW_SITTING,
) -> datetime:
    run_date = fake_parliament.new_sitting_date + timedelta(days=days_after_new_sitting)
    return datetime(
        run_date.year,
        run_date.month,
        run_date.day,
        _SINGAPORE_RUN_HOUR,
        tzinfo=SINGAPORE_TIMEZONE,
    ).astimezone(timezone.utc)


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


def _set_new_parliament_number(
    fake_parliament: FakeParliament, parliament_number: int
) -> None:
    for search_result in fake_parliament.new_search_results:
        search_result["parlNo"] = str(parliament_number)
    fake_parliament.new_sitting["metadata"]["parlimentNO"] = parliament_number


def _get_first_new_report_id(fake_parliament: FakeParliament) -> str:
    return fake_parliament.new_search_results[0]["reportId"]


def _get_new_topic_ids(fake_parliament: FakeParliament) -> set[str]:
    return {
        get_topic_id(
            search_result["reportId"],
            search_result["htmlFileName"],
            search_result["reportVersion"],
        )
        for search_result in fake_parliament.new_search_results
    }


def _get_new_contents(fake_parliament: FakeParliament) -> list[str]:
    return [
        fake_parliament.report_id_to_topic[search_result["reportId"]]["resultHTML"][
            "content"
        ]
        for search_result in fake_parliament.new_search_results
    ]


def _assert_nothing_written(
    scratch_engine: Engine, row_counts_before: dict[str, int]
) -> None:
    assert _get_row_counts(scratch_engine) == row_counts_before


def _assert_success_pinged(alerts: _AlertRecorder) -> None:
    assert alerts.pings == [_PING_URL]
    assert alerts.failure_pings == []


def _assert_failure_pinged(alerts: _AlertRecorder) -> None:
    assert alerts.failure_pings == [_PING_URL]
    assert alerts.pings == []


def _assert_halted(
    scratch_engine: Engine, alerts: _AlertRecorder, row_counts_before: dict[str, int]
) -> RefreshRun:
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.HALTED
    assert refresh_run.halt_reason is not None
    assert refresh_run.failure_reason is None
    assert all(getattr(refresh_run, column) == 0 for column in _ADDED_COUNT_COLUMNS)
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh halted.")
    _assert_failure_pinged(alerts)
    return refresh_run


def _assert_failed(
    scratch_engine: Engine,
    alerts: _AlertRecorder,
    row_counts_before: dict[str, int],
    error_name: str,
) -> RefreshRun:
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.FAILED
    assert refresh_run.failure_reason is not None
    assert refresh_run.failure_reason.startswith(error_name)
    assert refresh_run.finished_at is not None
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh failed.")
    assert error_name in alerts.messages[0]
    _assert_failure_pinged(alerts)
    return refresh_run


def _assert_rows_added(
    scratch_engine: Engine, row_counts_before: dict[str, int], refresh_run: RefreshRun
) -> None:
    row_counts_after = _get_row_counts(scratch_engine)
    assert (
        row_counts_after["HansardWebsiteResponse"]
        - row_counts_before["HansardWebsiteResponse"]
        == refresh_run.website_responses_added
    )
    assert (
        row_counts_after["Report"] - row_counts_before["Report"]
        == refresh_run.reports_added
    )
    assert (
        row_counts_after["Speech"] - row_counts_before["Speech"]
        == refresh_run.speeches_added
    )
    assert (
        row_counts_after["Sitting"] - row_counts_before["Sitting"]
        == refresh_run.sittings_added
    )
    assert (
        row_counts_after["Attendance"] - row_counts_before["Attendance"]
        == refresh_run.attendances_added
    )


def _raise_database_error(*args: object) -> None:
    raise SQLAlchemyError(_DATABASE_ERROR)


def _skip_vacuum_analyze(*args: object) -> None:
    pass


def _get_vacuum_counts(scratch_engine: Engine) -> list[int]:
    with Session(scratch_engine) as session:
        return [
            CRUDSpeech(session).get_vacuum_count(),
            CRUDReport(session).get_vacuum_count(),
            CRUDAttendance(session).get_vacuum_count(),
        ]


def test_clean_run_adds_rows_and_links_them(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

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
    parliament_group = next(
        group for group in groups if group["group"] == "Parliament 14"
    )
    assert "zero_row_report_count" in parliament_group
    assert parliament_group["report_types"] != []
    assert (
        len([message for message in alerts.messages if _SUMMARY_RE.match(message)]) == 1
    )
    _assert_success_pinged(alerts)
    with Session(scratch_engine) as session:
        new_sitting = session.exec(
            select(Sitting).where(
                Sitting.sitting_date
                == get_sitting_date_key(fake_parliament.new_sitting_date)
            )
        ).one()
        assert new_sitting.id is not None
        assert new_sitting.sections is not None
        new_raw_sitting = session.exec(
            select(HansardSittingDateResponse).where(
                HansardSittingDateResponse.sitting_date == new_sitting.sitting_date
            )
        ).one()
        assert new_raw_sitting.sections == new_sitting.sections
        assert refresh_run.attendances_linked > 0
        assert refresh_run.attendances_linked == CRUDAttendance(
            session
        ).get_count_by_sitting_ids_and_speaker_id_not_null([new_sitting.id])
        new_report_ids = {
            search_result["reportId"]
            for search_result in fake_parliament.new_search_results
        }
        speech_report_rows = session.exec(
            select(Speech.sitting_date, Report.sitting_date)
            .join(Report, col(Speech.report_id) == col(Report.id))
            .where(col(Report.report_id).in_(new_report_ids))
        ).all()
        assert speech_report_rows != []
        for speech_sitting_date, report_sitting_date in speech_report_rows:
            assert speech_sitting_date == report_sitting_date
        stored_report_ids = [
            report.id
            for report in session.exec(
                select(Report).where(col(Report.report_id).not_in(new_report_ids))
            ).all()
            if report.id is not None
        ]
        assert all(
            speech_row.speaker_id is None
            for speech_row in CRUDSpeech(session).get_rows_by_report_ids(
                stored_report_ids
            )
        )
        stored_sitting = session.exec(
            select(Sitting).where(
                Sitting.sitting_date
                == get_sitting_date_key(fake_parliament.stored_sitting_date)
            )
        ).one()
        assert stored_sitting.id is not None
        assert (
            CRUDAttendance(session).get_count_by_sitting_ids_and_speaker_id_not_null(
                [stored_sitting.id]
            )
            == 0
        )
        new_question_report_ids = {
            search_result["reportId"]
            for search_result in fake_parliament.new_search_results
            if search_result["reportType"] in REPORT_ASKER_REPORT_TYPES
        }
        report_id_asker_names = [
            (report_id, asker_name)
            for report_id, asker_name in session.exec(
                select(Report.report_id, Speaker.name)
                .join(ReportAsker, col(ReportAsker.report_id) == col(Report.id))
                .join(Speaker, col(ReportAsker.speaker_id) == col(Speaker.id))
            ).all()
        ]
        assert len(report_id_asker_names) == len(new_question_report_ids)
        assert {
            report_id for report_id, _ in report_id_asker_names
        } == new_question_report_ids
        assert (
            "written-answer-na-17735#",
            "Jamus Jerome Lim",
        ) in report_id_asker_names
        report_id_asker_participant_names = [
            (report_id, participant_name)
            for report_id, participant_name in session.exec(
                select(Report.report_id, Speaker.name)
                .join(
                    ReportParticipant,
                    col(ReportParticipant.report_id) == col(Report.id),
                )
                .join(Speaker, col(ReportParticipant.speaker_id) == col(Speaker.id))
                .where(
                    col(ReportParticipant.role).in_(
                        [ParticipantRole.ASKER, ParticipantRole.ABSENT_FILER]
                    )
                )
            ).all()
        ]
        assert sorted(report_id_asker_participant_names) == sorted(
            report_id_asker_names
        )


def _add_pointer_to_first_new_report(fake_parliament: FakeParliament) -> str:
    report_id = _get_first_new_report_id(fake_parliament)
    result_html = fake_parliament.report_id_to_topic[report_id]["resultHTML"]
    result_html["content"] += (
        f'<p><a href="/search/search/download?value={_ATTACHED_FILE_ADDRESS}">'
        "Annex A</a></p>"
    )
    return report_id


def _add_annexure_to_sitting(sitting_body: dict) -> None:
    sitting_body["annexureList"] = [
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


def _get_attached_file_counts(scratch_engine: Engine) -> list[int]:
    with Session(scratch_engine) as session:
        return [
            session.exec(select(func.count()).select_from(table)).one()
            for table in (AttachedFile, AttachedFilePointer)
        ]


def _get_pointer_file_ids(
    scratch_engine: Engine, sprs_report_id: str
) -> list[Optional[int]]:
    with Session(scratch_engine) as session:
        return list(
            session.exec(
                select(AttachedFilePointer.attached_file_id)
                .where(AttachedFilePointer.sprs_report_id == sprs_report_id)
                .order_by(col(AttachedFilePointer.ordinal))
            ).all()
        )


def _seed_stored_attached_file(
    session: Session, fake_parliament: FakeParliament
) -> int:
    stored_sitting = session.exec(
        select(Sitting).where(
            Sitting.sitting_date
            == get_sitting_date_key(fake_parliament.stored_sitting_date)
        )
    ).one()
    assert stored_sitting.id is not None
    attached_file = AttachedFile(
        kind=AttachedFileKind.ANNEX,
        sprs_file_id=_ATTACHED_FILE_ID,
        printed_title="Annex A",
        printed_file_path=f"d:/apps/reports/solr_files/{_ATTACHED_FILE_ADDRESS}",
        file_name="annex-Refresh Test.pdf",
        download_value=_ATTACHED_FILE_ADDRESS,
        sitting_id=stored_sitting.id,
    )
    session.add(attached_file)
    session.commit()
    assert attached_file.id is not None
    return attached_file.id


def test_new_report_pointer_ties_to_a_stored_file(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    seed_stored(scratch_session)
    stored_file_id = _seed_stored_attached_file(scratch_session, fake_parliament)
    report_id = _add_pointer_to_first_new_report(fake_parliament)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert _get_pointer_file_ids(scratch_engine, report_id) == [stored_file_id]
    assert _get_attached_file_counts(scratch_engine) == [_FIXTURE_FILE_COUNT + 1, 1]


def test_new_report_without_text_gives_no_pointers(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    seed_stored(scratch_session)
    atbp_report_id = fake_parliament.new_search_results[-1]["reportId"]
    fake_parliament.new_search_results[-1]["reportType"] = ReportType.ATBP
    fake_parliament.report_id_to_topic[atbp_report_id] = {
        "resultHTML": {"content": None}
    }

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    with Session(scratch_engine) as session:
        assert (
            session.exec(
                select(Report.content).where(Report.report_id == atbp_report_id)
            ).one()
            is None
        )
    assert _get_attached_file_counts(scratch_engine) == [_FIXTURE_FILE_COUNT, 0]


def test_sitting_that_arrives_after_its_report_ties_the_stored_pointer(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    seed_stored(scratch_session)
    scratch_session.add(
        AttachedFilePointer(
            ordinal=1,
            printed_text="Annex A",
            href=f"/search/search/download?value={_ATTACHED_FILE_ADDRESS}",
            shape=AttachedFilePointerShape.DATED,
            download_value=_ATTACHED_FILE_ADDRESS,
            sprs_report_id=_STORED_REPORT_ID,
        )
    )
    scratch_session.commit()
    _add_annexure_to_sitting(fake_parliament.new_sitting)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    with Session(scratch_engine) as session:
        new_file_id = session.exec(
            select(AttachedFile.id).where(
                AttachedFile.download_value == _ATTACHED_FILE_ADDRESS
            )
        ).one()
    assert _get_pointer_file_ids(scratch_engine, _STORED_REPORT_ID) == [new_file_id]


def test_pointer_whose_file_never_arrives_stays_untied(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    seed_stored(scratch_session)
    report_id = _add_pointer_to_first_new_report(fake_parliament)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert _get_pointer_file_ids(scratch_engine, report_id) == [None]
    assert _get_attached_file_counts(scratch_engine) == [_FIXTURE_FILE_COUNT, 1]


def test_halt_after_attached_files_are_written_leaves_no_file_or_pointer(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    new_contents = _get_new_contents(fake_parliament)
    speaker_names_to_drop = frozenset(
        speaker_row["name"]
        for speaker_row in load_speaker_rows()
        if any(speaker_row["name"] in content for content in new_contents)
    )
    seed_stored(scratch_session, speaker_names_to_drop)
    row_counts_before = _get_row_counts(scratch_engine)
    _add_pointer_to_first_new_report(fake_parliament)
    _add_annexure_to_sitting(fake_parliament.new_sitting)
    attached_file_counts_at_write: list[list[int]] = []
    populate_attached_files = refresh_runs.populate_attached_files

    def record_and_populate_attached_files(
        session: Session, report_ids: list[int], sitting_ids: list[int]
    ) -> None:
        populate_attached_files(session, report_ids, sitting_ids)
        attached_file_counts_at_write.append(
            [
                session.exec(select(func.count()).select_from(table)).one()
                for table in (AttachedFile, AttachedFilePointer)
            ]
        )

    monkeypatch.setattr(
        refresh_runs, "populate_attached_files", record_and_populate_attached_files
    )

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.HALTED
    _assert_halted(scratch_engine, alerts, row_counts_before)
    assert attached_file_counts_at_write[-1] == [_FIXTURE_FILE_COUNT + 1, 1]
    assert _get_attached_file_counts(scratch_engine) == [0, 0]


def test_clean_run_with_no_pointers_adds_none(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    seed_stored(scratch_session)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert _get_attached_file_counts(scratch_engine) == [_FIXTURE_FILE_COUNT, 0]


def test_run_that_adds_nothing_sends_no_message(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)
    row_counts_before = _get_row_counts(scratch_engine)
    alerts.messages.clear()
    alerts.pings.clear()
    alerts.failure_pings.clear()

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    second_run = _get_refresh_runs(scratch_engine)[-1]
    assert second_run.status == RefreshRunStatus.SUCCEEDED
    assert all(getattr(second_run, column) == 0 for column in _ADDED_COUNT_COLUMNS)
    assert second_run.figures is not None
    assert second_run.reports_changed == 0
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert alerts.messages == []
    _assert_success_pinged(alerts)


def test_clean_run_vacuums_after_the_data_commit_and_before_it_succeeds(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    vacuum_counts_before = _get_vacuum_counts(scratch_engine)
    new_report_ids = {
        search_result["reportId"]
        for search_result in fake_parliament.new_search_results
    }
    vacuum_analyze_speech = CRUDSpeech.vacuum_analyze
    run_statuses_at_vacuum: list[str] = []
    new_report_counts_at_vacuum: list[int] = []

    def record_and_vacuum_analyze_speech(crud_speech: CRUDSpeech) -> None:
        with Session(scratch_engine) as session:
            run_statuses_at_vacuum.append(session.exec(select(RefreshRun.status)).one())
            new_report_counts_at_vacuum.append(
                session.exec(
                    select(func.count())
                    .select_from(Report)
                    .where(col(Report.report_id).in_(new_report_ids))
                ).one()
            )
        vacuum_analyze_speech(crud_speech)

    monkeypatch.setattr(CRUDSpeech, "vacuum_analyze", record_and_vacuum_analyze_speech)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert run_statuses_at_vacuum == [RefreshRunStatus.RUNNING]
    assert new_report_counts_at_vacuum == [len(new_report_ids)]
    assert _get_vacuum_counts(scratch_engine) == [
        vacuum_count + 1 for vacuum_count in vacuum_counts_before
    ]
    _assert_success_pinged(alerts)


def test_run_that_adds_nothing_still_vacuums(
    scratch_engine: Engine, scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    seed_stored(scratch_session)
    refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)
    vacuum_counts_before = _get_vacuum_counts(scratch_engine)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert _get_refresh_runs(scratch_engine)[-1].speeches_added == 0
    assert _get_vacuum_counts(scratch_engine) == [
        vacuum_count + 1 for vacuum_count in vacuum_counts_before
    ]


def test_skipped_vacuum_fails_the_run_and_keeps_its_rows(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    monkeypatch.setattr(CRUDSpeech, "vacuum_analyze", _skip_vacuum_analyze)

    with pytest.raises(HansardRefreshRunError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.FAILED
    assert refresh_run.failure_reason is not None
    assert refresh_run.failure_reason.startswith(
        "After the data commit: HansardRefreshRunError: VACUUM (ANALYZE) did not run on speech"
    )
    assert refresh_run.speeches_added > 0
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    failure_messages = [
        message
        for message in alerts.messages
        if message.startswith("Hansard refresh failed.")
    ]
    assert len(failure_messages) == 1
    assert "did not run on speech" in failure_messages[0]
    assert (
        len([message for message in alerts.messages if _SUMMARY_RE.match(message)]) == 1
    )
    _assert_failure_pinged(alerts)


def test_vacuum_database_error_fails_the_run_and_keeps_its_rows(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)

    def vacuum_analyze_missing_table(crud_report: CRUDReport) -> None:
        crud_report.session.connection(
            execution_options={"isolation_level": "AUTOCOMMIT"}
        ).execute(text(_MISSING_TABLE_VACUUM))

    monkeypatch.setattr(CRUDReport, "vacuum_analyze", vacuum_analyze_missing_table)

    with pytest.raises(SQLAlchemyError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.FAILED
    assert refresh_run.failure_reason is not None
    assert refresh_run.failure_reason.startswith(
        "After the data commit: ProgrammingError"
    )
    assert _MISSING_TABLE_VACUUM in refresh_run.failure_reason
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    failure_messages = [
        message
        for message in alerts.messages
        if message.startswith("Hansard refresh failed.")
    ]
    assert failure_messages == [
        "Hansard refresh failed. ProgrammingError after the data commit"
    ]
    _assert_failure_pinged(alerts)


def test_clean_run_links_reports_after_the_vacuum(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    vacuum_analyze_speech = CRUDSpeech.vacuum_analyze
    speech_vacuum_count = 0
    speech_vacuum_counts_at_link: list[int] = []
    run_statuses_at_link: list[str] = []

    def record_and_vacuum_analyze_speech(crud_speech: CRUDSpeech) -> None:
        nonlocal speech_vacuum_count
        vacuum_analyze_speech(crud_speech)
        speech_vacuum_count += 1

    def record_and_populate_report_links(session: Session) -> int:
        speech_vacuum_counts_at_link.append(speech_vacuum_count)
        run_statuses_at_link.append(_get_only_refresh_run(scratch_engine).status)
        return 0

    monkeypatch.setattr(CRUDSpeech, "vacuum_analyze", record_and_vacuum_analyze_speech)
    monkeypatch.setattr(
        refresh_runs, "populate_report_links", record_and_populate_report_links
    )

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert speech_vacuum_counts_at_link == [1]
    assert run_statuses_at_link == [RefreshRunStatus.RUNNING]
    assert _get_only_refresh_run(scratch_engine).status == RefreshRunStatus.SUCCEEDED
    _assert_success_pinged(alerts)


def test_stale_report_links_are_alerted(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    monkeypatch.setattr(refresh_runs, "populate_report_links", lambda session: 3)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert build_stale_report_links_message(3) in alerts.messages
    _assert_success_pinged(alerts)


def test_run_with_no_stale_report_links_sends_no_such_alert(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    monkeypatch.setattr(refresh_runs, "populate_report_links", lambda session: 0)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert not [
        message for message in alerts.messages if "report links differ" in message
    ]


def test_report_link_failure_fails_the_run_and_keeps_its_rows(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)

    def populate_report_links_that_fails(session: Session) -> int:
        raise SQLAlchemyError("report link failure")

    monkeypatch.setattr(
        refresh_runs, "populate_report_links", populate_report_links_that_fails
    )

    with pytest.raises(SQLAlchemyError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.FAILED
    assert refresh_run.failure_reason is not None
    assert refresh_run.failure_reason.startswith(
        "After the data commit: SQLAlchemyError"
    )
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    failure_messages = [
        message
        for message in alerts.messages
        if message.startswith("Hansard refresh failed.")
    ]
    assert failure_messages == [
        "Hansard refresh failed. SQLAlchemyError after the data commit"
    ]
    _assert_failure_pinged(alerts)


def test_new_parliament_number_halts(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _set_new_parliament_number(fake_parliament, _NEW_PARLIAMENT_NUMBER)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert str(_NEW_PARLIAMENT_NUMBER) in refresh_run.halt_reason
    new_topic_ids = _get_new_topic_ids(fake_parliament)
    assert not any(
        topic_id in new_topic_ids for topic_id in fake_parliament.topic_calls
    )
    assert not any(
        parse_sitting_date(sitting_call).month == fake_parliament.new_sitting_date.month
        for sitting_call in fake_parliament.sitting_calls
    )


def test_new_parliament_number_in_sitting_body_halts(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    fake_parliament.new_sitting["metadata"]["parlimentNO"] = _NEW_PARLIAMENT_NUMBER

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert str(_NEW_PARLIAMENT_NUMBER) in refresh_run.halt_reason
    assert fake_parliament.topic_calls != []


def test_allowed_parliament_number_runs(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    scratch_session.add_all(
        [
            Speaker(**{**speaker_row, "parliament_number": _NEW_PARLIAMENT_NUMBER})
            for speaker_row in load_speaker_rows()
        ]
    )
    scratch_session.commit()
    _set_new_parliament_number(fake_parliament, _NEW_PARLIAMENT_NUMBER)
    row_counts_before = _get_row_counts(scratch_engine)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), _NEW_PARLIAMENT_NUMBER
    )

    assert status == RefreshRunStatus.SUCCEEDED
    refresh_run = _get_only_refresh_run(scratch_engine)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    assert refresh_run.status == RefreshRunStatus.SUCCEEDED
    assert refresh_run.reports_added == len(fake_parliament.new_search_results)
    assert (
        len([message for message in alerts.messages if _SUMMARY_RE.match(message)]) == 1
    )
    _assert_success_pinged(alerts)


def test_other_parliament_number_halts_when_one_is_allowed(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _set_new_parliament_number(fake_parliament, _OTHER_PARLIAMENT_NUMBER)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), _NEW_PARLIAMENT_NUMBER
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert str(_OTHER_PARLIAMENT_NUMBER) in refresh_run.halt_reason


def test_field_mapping_failure_halts(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    report_id = _get_first_new_report_id(fake_parliament)
    content = fake_parliament.report_id_to_topic[report_id]["resultHTML"]["content"]
    fake_parliament.report_id_to_topic[report_id] = {"htmlContent": content}

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert "field mapping check" in refresh_run.halt_reason


def test_sitting_field_mapping_failure_halts(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    assert fake_parliament.new_sitting["metadata"]["sessionNO"] not in (None, "")
    build_new_hansard_sitting_date_response = (
        hansard_sitting_date_response_service.build_new_hansard_sitting_date_response
    )

    def build_lossy_sitting_date_response(
        hansard_report_response: HansardReportNewResponse, sitting_date: str
    ) -> HansardSittingDateResponse:
        hansard_sitting_date_response = build_new_hansard_sitting_date_response(
            hansard_report_response, sitting_date
        )
        hansard_sitting_date_response.session_no = None
        return hansard_sitting_date_response

    monkeypatch.setattr(
        hansard_sitting_date_response_service,
        "build_new_hansard_sitting_date_response",
        build_lossy_sitting_date_response,
    )

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert "sessionNO" in refresh_run.halt_reason


def _assert_attached_file_list_halt(
    scratch_engine: Engine,
    alerts: _AlertRecorder,
    row_counts_before: dict[str, int],
    sitting_date_key: str,
    status: RefreshRunStatus,
) -> None:
    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert sitting_date_key in refresh_run.halt_reason
    assert "annexureList" in refresh_run.halt_reason
    assert "filePath" in refresh_run.halt_reason
    assert _get_attached_file_counts(scratch_engine) == [0, 0]


def test_attached_file_list_missing_file_path_halts(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _add_annexure_to_sitting(fake_parliament.new_sitting)
    del fake_parliament.new_sitting["annexureList"][0]["filePath"]

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    _assert_attached_file_list_halt(
        scratch_engine,
        alerts,
        row_counts_before,
        get_sitting_date_key(fake_parliament.new_sitting_date),
        status,
    )


def test_attached_file_list_path_without_solr_files_halts(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _add_annexure_to_sitting(fake_parliament.new_sitting)
    fake_parliament.new_sitting["annexureList"][0]["filePath"] = "d:/apps/Annex.pdf"

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    _assert_attached_file_list_halt(
        scratch_engine,
        alerts,
        row_counts_before,
        get_sitting_date_key(fake_parliament.new_sitting_date),
        status,
    )


def test_unlinked_share_over_limit_halts(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    new_contents = _get_new_contents(fake_parliament)
    speaker_names_to_drop = frozenset(
        speaker_row["name"]
        for speaker_row in load_speaker_rows()
        if any(speaker_row["name"] in content for content in new_contents)
    )
    seed_stored(scratch_session, speaker_names_to_drop)
    row_counts_before = _get_row_counts(scratch_engine)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _assert_halted(scratch_engine, alerts, row_counts_before)
    assert refresh_run.halt_reason is not None
    assert "% of new speech rows" in refresh_run.halt_reason
    assert any(
        speaker_name in refresh_run.halt_reason
        for speaker_name in speaker_names_to_drop
    )
    assert any(
        speaker_name in alerts.messages[0] for speaker_name in speaker_names_to_drop
    )


def test_missing_member_is_stored_unlinked(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    report_id, match = next(
        (search_result["reportId"], match)
        for search_result in fake_parliament.new_search_results
        if (
            match := _STRONG_LABEL_RE.search(
                fake_parliament.report_id_to_topic[search_result["reportId"]][
                    "resultHTML"
                ]["content"]
            )
        )
        is not None
    )
    topic = fake_parliament.report_id_to_topic[report_id]["resultHTML"]
    topic["content"] = topic["content"].replace(
        match.group(0), f"<strong>{_UNREGISTERED_LABEL}</strong>", 1
    )

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    refresh_run = _get_only_refresh_run(scratch_engine)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    assert refresh_run.status == RefreshRunStatus.SUCCEEDED
    with Session(scratch_engine) as session:
        unregistered_speeches = session.exec(
            select(Speech).where(Speech.speaker == _UNREGISTERED_LABEL)
        ).all()
    assert unregistered_speeches != []
    assert all(speech.speaker_id is None for speech in unregistered_speeches)
    assert any(
        message.startswith("Speaker labels with no registry match")
        and _UNREGISTERED_LABEL in message
        for message in alerts.messages
    )
    _assert_success_pinged(alerts)


def test_changed_report_in_window_alerts_and_keeps_text(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    stored_report_id = fake_parliament.stored_search_results[0]["reportId"]
    with Session(scratch_engine) as session:
        stored_content = session.exec(
            select(HansardWebsiteResponse.content).where(
                HansardWebsiteResponse.report_id == stored_report_id
            )
        ).one()
        stored_markdown = session.exec(
            select(Report.markdown_content).where(Report.report_id == stored_report_id)
        ).one()
    assert stored_content is not None
    assert _FIRST_WORD_RE.search(stored_content)
    fake_parliament.report_id_to_topic[stored_report_id] = {
        "resultHTML": {"content": _FIRST_WORD_RE.sub("a", stored_content, count=1)}
    }

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    refresh_run = _get_only_refresh_run(scratch_engine)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    assert refresh_run.reports_changed == 1
    assert refresh_run.reports_rechecked == len(fake_parliament.stored_search_results)
    assert any(
        message.startswith(f"Report {stored_report_id} of")
        and "changed on SPRS" in message
        for message in alerts.messages
    )
    with Session(scratch_engine) as session:
        assert (
            session.exec(
                select(HansardWebsiteResponse.content).where(
                    HansardWebsiteResponse.report_id == stored_report_id
                )
            ).one()
            == stored_content
        )
        assert (
            session.exec(
                select(Report.markdown_content).where(
                    Report.report_id == stored_report_id
                )
            ).one()
            == stored_markdown
        )
    _assert_success_pinged(alerts)


def test_report_without_text_is_held(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    held_report_id = _get_first_new_report_id(fake_parliament)
    fake_parliament.report_id_to_topic[held_report_id] = {
        "resultHTML": {"content": None}
    }

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    refresh_run = _get_only_refresh_run(scratch_engine)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    assert refresh_run.reports_held_without_text == 1
    assert refresh_run.reports_added == len(fake_parliament.new_search_results) - 1
    with Session(scratch_engine) as session:
        assert (
            session.exec(
                select(HansardWebsiteResponse).where(
                    HansardWebsiteResponse.report_id == held_report_id
                )
            ).all()
            == []
        )
    assert not any("still has no text" in message for message in alerts.messages)
    _assert_success_pinged(alerts)
    alerts.messages.clear()
    alerts.pings.clear()
    alerts.failure_pings.clear()

    second_day_now = _get_now(
        fake_parliament, _RECHECK_WINDOW_DAYS + _HELD_ALERT_DAY_OFFSET - 1
    )
    status = refresh_runs.populate_refresh_runs(scratch_session, second_day_now, None)

    assert status == RefreshRunStatus.SUCCEEDED
    assert _get_refresh_runs(scratch_engine)[-1].reports_held_without_text == 1
    assert any(
        message.startswith(f"Report {held_report_id} of")
        and "still has no text" in message
        for message in alerts.messages
    )
    _assert_success_pinged(alerts)


def test_run_where_every_topic_is_an_error_body_fails(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    for report_id in fake_parliament.report_id_to_topic:
        fake_parliament.report_id_to_topic[report_id] = {
            "errorMessage": "Internal error"
        }

    with pytest.raises(HansardRefreshFailureError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.FAILED
    assert refresh_run.failure_reason is not None
    assert "error bodies" in refresh_run.failure_reason
    assert refresh_run.reports_added == 0
    assert any(
        message.startswith("Hansard refresh failed.") for message in alerts.messages
    )
    _assert_failure_pinged(alerts)


@pytest.mark.parametrize(
    ("held_count", "is_alert_expected"),
    [(MAX_NEW_HITS_WITHOUT_TEXT, False), (MAX_NEW_HITS_WITHOUT_TEXT + 1, True)],
)
def test_many_new_hits_without_text_alert_the_same_day(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    held_count: int,
    is_alert_expected: bool,
) -> None:
    seed_stored(scratch_session)
    for search_result in fake_parliament.new_search_results[:held_count]:
        fake_parliament.report_id_to_topic[search_result["reportId"]] = {
            "resultHTML": {"content": None}
        }

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert (
        any("came back with no text" in message for message in alerts.messages)
        == is_alert_expected
    )
    _assert_success_pinged(alerts)


def test_gateway_failure_fails_the_run(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)

    async def raise_gateway_error(
        topic_id: str, client: httpx.AsyncClient
    ) -> HansardTopicResponse:
        raise HansardGatewayError(f"Topic request failed for {topic_id}")

    monkeypatch.setattr(
        refresh_runs, "get_hansard_topic_response_async", raise_gateway_error
    )

    with pytest.raises(HansardGatewayError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    refresh_run = _assert_failed(
        scratch_engine, alerts, row_counts_before, "HansardGatewayError"
    )
    assert refresh_run.failure_reason is not None
    assert "Topic request failed" in refresh_run.failure_reason


def test_unread_division_openings_are_alerted_once_for_the_run(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    monkeypatch.setattr(
        refresh_runs,
        "populate_divisions",
        lambda session, report_ids: [_UNREAD_REPORT_ID],
    )

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    division_messages = [
        message
        for message in alerts.messages
        if _UNREAD_DIVISION_ALERT_FRAGMENT in message
    ]
    assert len(division_messages) == 1
    assert f"report ids {_UNREAD_REPORT_ID}" in division_messages[0]


def test_a_division_failure_rolls_back_the_month(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)

    def raise_division_error(session: Session, report_ids: list[int]) -> list[int]:
        raise HansardRefreshRunError("division stage failed")

    monkeypatch.setattr(refresh_runs, "populate_divisions", raise_division_error)

    with pytest.raises(HansardRefreshRunError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    refresh_run = _assert_failed(
        scratch_engine, alerts, row_counts_before, "HansardRefreshRunError"
    )
    assert refresh_run.failure_reason is not None
    assert "division stage failed" in refresh_run.failure_reason


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


def _build_minutes_file_response(file_url: str) -> MinutesResponse:
    return MinutesResponse(
        url=file_url,
        status_code=200,
        content=(_MINUTES_FIXTURE_DIRECTORY / _MINUTES_PDF_FIXTURE).read_bytes(),
    )


def _list_minutes_file(
    fake_parliament: FakeParliament, sitting_date: date, file_id: str, file_name: str
) -> None:
    fake_parliament.minutes_index_page = build_live_index_page(
        [build_live_index_row(sitting_date, _MINUTES_FILE_NUMBER, file_id, file_name)]
    )
    file_url = f"{settings.minutes_media_url}/{file_id}/{file_name}"
    fake_parliament.file_url_to_response[file_url] = _build_minutes_file_response(
        file_url
    )


def test_held_hit_dates_reach_the_minutes_step(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    held_report_id = _get_first_new_report_id(fake_parliament)
    fake_parliament.report_id_to_topic[held_report_id] = {
        "resultHTML": {"content": None}
    }
    recorded_held_sitting_dates: list[set[date]] = []

    def record_held_sitting_dates(
        session: Session, held_sitting_dates: set[date]
    ) -> MinutesStepResult:
        recorded_held_sitting_dates.append(held_sitting_dates)
        return MinutesStepResult(0, 0, 0, [], [])

    monkeypatch.setattr(refresh_runs, "populate_minutes", record_held_sitting_dates)

    refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)

    assert recorded_held_sitting_dates == [{fake_parliament.new_sitting_date}]


def _assert_minutes_index_failure(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    error_type: type[HansardError],
) -> None:
    vacuum_counts_before = _get_vacuum_counts(scratch_engine)
    row_counts_before = _get_row_counts(scratch_engine)

    with pytest.raises(error_type):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.FAILED
    assert refresh_run.failure_reason is not None
    assert refresh_run.failure_reason.startswith(
        f"After the data commit: {error_type.__name__}"
    )
    assert refresh_run.figures is not None
    assert _get_vacuum_counts(scratch_engine) == [
        vacuum_count + 1 for vacuum_count in vacuum_counts_before
    ]
    assert refresh_run.reports_added > 0
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    _assert_failure_pinged(alerts)


def test_minutes_index_failure_fails_the_run_after_the_figures_and_the_vacuum(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    fake_parliament.minutes_index_error = HansardGatewayError("index down")

    _assert_minutes_index_failure(
        scratch_engine, scratch_session, fake_parliament, alerts, HansardGatewayError
    )


def test_minutes_to_review_are_alerted_when_a_run_with_no_new_rows_fails_at_the_figures(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)
    add_division_report(scratch_session, "MINUTES-REPORT", datetime(2018, 1, 11))
    scratch_session.commit()
    _list_minutes_file(
        fake_parliament, date(2018, 1, 11), _MINUTES_FILE_ID, _MINUTES_FILE_NAME
    )
    alerts.messages.clear()

    def fail_at_the_figures(session: Session) -> None:
        raise HansardRefreshFailureError("figures failed")

    monkeypatch.setattr(refresh_runs, "get_attribution_figures", fail_at_the_figures)

    with pytest.raises(HansardRefreshFailureError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    review_messages = [
        message for message in alerts.messages if _MINUTES_ALERT_FRAGMENT in message
    ]
    assert len(review_messages) == 1


def test_minutes_to_review_of_a_row_listed_before_the_run_are_alerted_after_a_failure(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)
    add_division_report(scratch_session, "MINUTES-REPORT", datetime(2018, 1, 11))
    scratch_session.add(
        Minutes(
            sitting_date=date(2018, 1, 11),
            status=MinutesStatus.LISTED,
            index_source=MinutesIndexSource.LIVE_PAGE,
            file_url=f"{settings.minutes_media_url}/{_MINUTES_FILE_ID}/{_MINUTES_FILE_NAME}",
            file_format=MinutesFileFormat.PDF,
        )
    )
    scratch_session.commit()
    _list_minutes_file(
        fake_parliament, date(2018, 1, 11), _MINUTES_FILE_ID, _MINUTES_FILE_NAME
    )
    alerts.messages.clear()

    def fail_at_the_figures(session: Session) -> None:
        raise HansardRefreshFailureError("figures failed")

    monkeypatch.setattr(refresh_runs, "get_attribution_figures", fail_at_the_figures)

    with pytest.raises(HansardRefreshFailureError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    review_messages = [
        message for message in alerts.messages if _MINUTES_ALERT_FRAGMENT in message
    ]
    assert len(review_messages) == 1


def test_non_200_index_answer_fails_the_run_the_same_way(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    fake_parliament.minutes_index_status = _NOT_FOUND_STATUS

    _assert_minutes_index_failure(
        scratch_engine,
        scratch_session,
        fake_parliament,
        alerts,
        HansardMinutesIndexError,
    )


def test_minutes_needing_review_are_alerted(
    scratch_session: Session, fake_parliament: FakeParliament, alerts: _AlertRecorder
) -> None:
    seed_stored(scratch_session)
    add_division_report(scratch_session, "MINUTES-REPORT", datetime(2018, 1, 11))
    scratch_session.commit()
    _list_minutes_file(
        fake_parliament, date(2018, 1, 11), _MINUTES_FILE_ID, _MINUTES_FILE_NAME
    )

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    review_messages = [
        message for message in alerts.messages if _MINUTES_ALERT_FRAGMENT in message
    ]
    assert len(review_messages) == 1
    assert "10 January 2018" in review_messages[0]


def test_minutes_step_emits_only_the_granted_statements(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        minutes_step,
        "get_minutes_pdf_text",
        lambda content: _MINUTES_DIVISION_TEXT_FIXTURE.read_text(encoding="utf-8"),
    )
    seed_stored(scratch_session)
    add_division_report(scratch_session, "MINUTES-REPORT", datetime(2018, 1, 10))
    scratch_session.add(
        Minutes(sitting_date=date(2018, 1, 10), status=MinutesStatus.NOT_YET_LISTED)
    )
    scratch_session.commit()
    _list_minutes_file(
        fake_parliament, date(2018, 1, 10), _MINUTES_FILE_ID, _MINUTES_FILE_NAME
    )
    recorded_statements: list[str] = []

    def record_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        is_many: bool,
    ) -> None:
        recorded_statements.append(statement)

    event.listen(scratch_engine, "before_cursor_execute", record_statement)
    try:
        minutes_step.populate_minutes(scratch_session, set())
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert _get_statement_problems(recorded_statements) == []
    observed_effects = {
        effect
        for statement in recorded_statements
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
        for statement in recorded_statements
        if _get_statement_effects(statement) == [("UPDATE", "minutes")]
    ]
    assert update_statements
    for update_statement in update_statements:
        set_match = _SET_CLAUSE_PATTERN.search(update_statement)
        assert set_match is not None
        assert _SET_COLUMN_PATTERN.findall(set_match.group(1))
    assert not {verb for verb, _ in observed_effects} & {"DELETE", "TRUNCATE", "GRANT"}


def test_the_daily_minutes_step_writes_divisions_in_the_file_commit(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        minutes_step,
        "get_minutes_pdf_text",
        lambda content: _MINUTES_DIVISION_TEXT_FIXTURE.read_text(encoding="utf-8"),
    )
    seed_stored(scratch_session)
    add_division_report(scratch_session, "MINUTES-REPORT", datetime(2018, 1, 10))
    scratch_session.add(
        Minutes(sitting_date=date(2018, 1, 10), status=MinutesStatus.NOT_YET_LISTED)
    )
    scratch_session.commit()
    _list_minutes_file(
        fake_parliament, date(2018, 1, 10), _MINUTES_FILE_ID, _MINUTES_FILE_NAME
    )

    minutes_step.populate_minutes(scratch_session, set())

    scratch_session.expire_all()
    stored_minutes = scratch_session.exec(
        select(Minutes).where(col(Minutes.sitting_date) == date(2018, 1, 10))
    ).one()
    assert stored_minutes.status == MinutesStatus.TEXT_STORED
    assert (
        scratch_session.exec(select(func.count()).select_from(MinutesDivision)).one()
        == _MINUTES_DIVISION_ROW_COUNT
    )


def test_the_daily_minutes_step_writes_the_breakdown_for_every_division_of_the_sitting(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        minutes_step,
        "get_minutes_pdf_text",
        lambda content: _MINUTES_DIVISION_TEXT_FIXTURE.read_text(encoding="utf-8"),
    )
    seed_stored(scratch_session)
    report = add_division_report(
        scratch_session, "MINUTES-REPORT", datetime(2018, 1, 10)
    )
    hansard_only_division = Division(
        sitting_date=date(2018, 1, 10),
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
    scratch_session.add(
        Minutes(sitting_date=date(2018, 1, 10), status=MinutesStatus.NOT_YET_LISTED)
    )
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
    _list_minutes_file(
        fake_parliament, date(2018, 1, 10), _MINUTES_FILE_ID, _MINUTES_FILE_NAME
    )

    minutes_step.populate_minutes(scratch_session, set())

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


def test_a_failed_division_step_leaves_the_file_listed_with_no_rows(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_division_step(session: Session, minutes_id: int) -> None:
        raise HansardWriteCheckError("The division step failed")

    monkeypatch.setattr(
        minutes_step,
        "get_minutes_pdf_text",
        lambda content: _MINUTES_DIVISION_TEXT_FIXTURE.read_text(encoding="utf-8"),
    )
    monkeypatch.setattr(minutes_step, "populate_minutes_divisions", fail_division_step)
    seed_stored(scratch_session)
    add_division_report(scratch_session, "MINUTES-REPORT", datetime(2018, 1, 10))
    scratch_session.add(
        Minutes(sitting_date=date(2018, 1, 10), status=MinutesStatus.NOT_YET_LISTED)
    )
    scratch_session.commit()
    _list_minutes_file(
        fake_parliament, date(2018, 1, 10), _MINUTES_FILE_ID, _MINUTES_FILE_NAME
    )

    with pytest.raises(HansardWriteCheckError):
        minutes_step.populate_minutes(scratch_session, set())

    scratch_session.rollback()
    stored_minutes = scratch_session.exec(
        select(Minutes).where(col(Minutes.sitting_date) == date(2018, 1, 10))
    ).one()
    assert stored_minutes.status == MinutesStatus.LISTED
    assert stored_minutes.extracted_text is None
    assert (
        scratch_session.exec(select(func.count()).select_from(MinutesDivision)).one()
        == 0
    )


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
    add_division_report(scratch_session, "MINUTES-REPORT", datetime(2018, 1, 11))
    scratch_session.commit()
    _list_minutes_file(
        fake_parliament, date(2018, 1, 11), _MINUTES_FILE_ID, _MINUTES_FILE_NAME
    )

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    scratch_session.expire_all()
    stored_minutes = scratch_session.exec(
        select(Minutes).where(col(Minutes.sitting_date) == date(2018, 1, 11))
    ).one()
    assert stored_minutes.status == MinutesStatus.NEEDS_REVIEW
    assert stored_minutes.status_note == UNREAD_DIVISION_STATUS_NOTE
    assert (
        scratch_session.exec(select(func.count()).select_from(MinutesDivision)).one()
        == 0
    )
    review_messages = [
        message for message in alerts.messages if _MINUTES_ALERT_FRAGMENT in message
    ]
    assert len(review_messages) == 1
    assert UNREAD_DIVISION_STATUS_NOTE in review_messages[0]


def test_a_minutes_file_that_cannot_be_fetched_is_alerted_once_and_the_run_succeeds(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    add_division_report(scratch_session, "MINUTES-REPORT", datetime(2018, 1, 11))
    scratch_session.commit()
    _list_minutes_file(
        fake_parliament, date(2018, 1, 11), _MINUTES_FILE_ID, _MINUTES_FILE_NAME
    )
    fake_parliament.file_url_to_response.clear()

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    scratch_session.expire_all()
    stored_minutes = scratch_session.exec(
        select(Minutes).where(col(Minutes.sitting_date) == date(2018, 1, 11))
    ).one()
    assert stored_minutes.status == MinutesStatus.LISTED
    not_fetched_messages = [
        message
        for message in alerts.messages
        if _MINUTES_NOT_FETCHED_ALERT_FRAGMENT in message
    ]
    assert len(not_fetched_messages) == 1
    assert "11 January 2018 (the request failed)" in not_fetched_messages[0]


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


def test_database_error_mid_write_fails_the_run(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    monkeypatch.setattr(CRUDSpeech, "add_many", _raise_database_error)

    with pytest.raises(SQLAlchemyError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    _assert_failed(scratch_engine, alerts, row_counts_before, "SQLAlchemyError")
    assert _DATABASE_HOST not in alerts.messages[0]


def test_failure_at_start_still_alerts_and_pings(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    monkeypatch.setattr(CRUDRefreshRun, "create", _raise_database_error)

    with pytest.raises(SQLAlchemyError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    assert _get_refresh_runs(scratch_engine) == []
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh failed.")
    assert "SQLAlchemyError" in alerts.messages[0]
    assert _DATABASE_HOST not in alerts.messages[0]
    _assert_failure_pinged(alerts)


def test_finish_guard_error_in_halt_still_alerts_and_pings(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _set_new_parliament_number(fake_parliament, _NEW_PARLIAMENT_NUMBER)

    is_run_marked_failed = False

    def mark_running_run_failed() -> None:
        nonlocal is_run_marked_failed
        if is_run_marked_failed:
            return
        with Session(scratch_engine) as session:
            running_run = session.exec(
                select(RefreshRun).where(RefreshRun.status == RefreshRunStatus.RUNNING)
            ).one()
            running_run.status = RefreshRunStatus.FAILED
            session.add(running_run)
            session.commit()
        is_run_marked_failed = True

    fake_parliament.on_search = mark_running_run_failed

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.FAILED
    assert refresh_run.halt_reason is None
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh halted.")
    _assert_failure_pinged(alerts)


def test_finish_database_error_in_halt_still_alerts_and_pings(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _set_new_parliament_number(fake_parliament, _NEW_PARLIAMENT_NUMBER)
    monkeypatch.setattr(CRUDRefreshRun, "get_by_id_for_update", _raise_database_error)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.RUNNING
    _assert_nothing_written(scratch_engine, row_counts_before)
    assert len(alerts.messages) == 1
    assert alerts.messages[0].startswith("Hansard refresh halted.")
    assert _DATABASE_HOST not in alerts.messages[0]
    _assert_failure_pinged(alerts)


def test_unset_alert_settings_send_nothing(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    monkeypatch.setattr(settings, "telegram_bot_token", None)
    monkeypatch.setattr(settings, "telegram_chat_id", None)
    monkeypatch.setattr(settings, "healthchecks_ping_url", None)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    assert _get_only_refresh_run(scratch_engine).status == RefreshRunStatus.SUCCEEDED
    _assert_rows_added(
        scratch_engine, row_counts_before, _get_only_refresh_run(scratch_engine)
    )
    assert alerts.messages == []
    assert alerts.pings == []
    assert alerts.failure_pings == []


def _seed_running_run(scratch_session: Session, started_at: datetime) -> int:
    refresh_run = RefreshRun(started_at=started_at)
    scratch_session.add(refresh_run)
    scratch_session.commit()
    assert refresh_run.id is not None
    return refresh_run.id


def _get_refresh_run(
    scratch_engine: Engine, refresh_run_id: int
) -> Optional[RefreshRun]:
    with Session(scratch_engine) as session:
        return session.get(RefreshRun, refresh_run_id)


def test_fresh_running_row_blocks_a_second_run(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
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
    _assert_failure_pinged(alerts)


def test_stale_running_row_is_marked_failed(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
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
    _assert_rows_added(
        scratch_engine, row_counts_before, _get_refresh_runs(scratch_engine)[-1]
    )
    assert (
        len([message for message in alerts.messages if _SUMMARY_RE.match(message)]) == 1
    )
    _assert_success_pinged(alerts)


def _get_october_now() -> datetime:
    return datetime(
        _OCTOBER_RUN_DATE.year,
        _OCTOBER_RUN_DATE.month,
        _OCTOBER_RUN_DATE.day,
        _SINGAPORE_RUN_HOUR,
        tzinfo=SINGAPORE_TIMEZONE,
    ).astimezone(timezone.utc)


def _add_october_hit(fake_parliament: FakeParliament, parliament_number: int) -> None:
    october_search_result = copy.deepcopy(fake_parliament.new_search_results[0])
    october_topic = copy.deepcopy(
        fake_parliament.report_id_to_topic[october_search_result["reportId"]]
    )
    october_topic["resultHTML"]["content"] = _STRONG_TEXT_RE.sub(
        f"<strong>{_UNREGISTERED_LABEL}</strong>",
        october_topic["resultHTML"]["content"],
    )
    october_search_result["reportId"] = _OCTOBER_REPORT_ID
    october_search_result["sittingDate"] = _OCTOBER_SITTING_DATE_KEY
    october_search_result["parlNo"] = str(parliament_number)
    fake_parliament.new_search_results.append(october_search_result)
    fake_parliament.report_id_to_topic[_OCTOBER_REPORT_ID] = october_topic


def _get_september_report_count(fake_parliament: FakeParliament) -> int:
    return len(
        [
            search_result
            for search_result in fake_parliament.new_search_results
            if search_result["reportId"] != _OCTOBER_REPORT_ID
        ]
    )


def test_halt_in_a_later_month_keeps_the_earlier_months(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _add_october_hit(fake_parliament, _OTHER_PARLIAMENT_NUMBER)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_october_now(), None
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.HALTED
    assert refresh_run.reports_added == _get_september_report_count(fake_parliament)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    assert refresh_run.speeches_added > 0
    assert (
        len(
            [
                message
                for message in alerts.messages
                if message.startswith("Hansard refresh halted.")
            ]
        )
        == 1
    )
    assert (
        len([message for message in alerts.messages if _SUMMARY_RE.match(message)]) == 1
    )
    _assert_failure_pinged(alerts)


def test_rerun_after_a_failure_resumes_without_refetching(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    is_october_search_failed = False

    def fail_the_first_october_search(
        from_date: date, to_date: date
    ) -> list[HansardSearchResult]:
        nonlocal is_october_search_failed
        if from_date.month == _OCTOBER_MONTH and not is_october_search_failed:
            is_october_search_failed = True
            raise HansardGatewayError("Search request failed for page 1")
        return fake_parliament.get_all_hansard_search_results(from_date, to_date)

    monkeypatch.setattr(
        refresh_runs, "get_all_hansard_search_results", fail_the_first_october_search
    )

    with pytest.raises(HansardGatewayError):
        refresh_runs.populate_refresh_runs(scratch_session, _get_october_now(), None)

    failed_run = _get_only_refresh_run(scratch_engine)
    assert failed_run.status == RefreshRunStatus.FAILED
    assert failed_run.reports_added == len(fake_parliament.new_search_results)
    assert failed_run.failure_reason is not None
    assert failed_run.failure_reason.startswith("After the data commit")
    fake_parliament.search_calls.clear()
    fake_parliament.sitting_calls.clear()
    fake_parliament.topic_calls.clear()

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_october_now(), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    second_run = _get_refresh_runs(scratch_engine)[-1]
    assert second_run.status == RefreshRunStatus.SUCCEEDED
    assert second_run.reports_added == 0
    new_topic_ids = _get_new_topic_ids(fake_parliament)
    assert not any(
        topic_id in new_topic_ids for topic_id in fake_parliament.topic_calls
    )
    assert fake_parliament.search_calls[0][0] == _RESUMED_PROBE_START_DATE
    assert (
        get_sitting_date_key(fake_parliament.new_sitting_date)
        not in fake_parliament.sitting_calls
    )


def test_unlinked_share_halt_in_a_later_month_records_only_committed_counts(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _add_october_hit(fake_parliament, _PREVIOUS_PARLIAMENT_NUMBER)

    def get_unpublished_october_sitting(
        sitting_date: str,
    ) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
        if sitting_date == _OCTOBER_SITTING_DATE_KEY:
            return HansardReportNewResponse()
        return fake_parliament.get_hansard_report_response(sitting_date)

    monkeypatch.setattr(
        refresh_runs, "get_hansard_report_response", get_unpublished_october_sitting
    )

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_october_now(), None
    )

    assert status == RefreshRunStatus.HALTED
    refresh_run = _get_only_refresh_run(scratch_engine)
    assert refresh_run.status == RefreshRunStatus.HALTED
    assert refresh_run.halt_reason is not None
    assert "% of new speech rows" in refresh_run.halt_reason
    assert _UNREGISTERED_LABEL in refresh_run.halt_reason
    assert refresh_run.reports_added == _get_september_report_count(fake_parliament)
    _assert_rows_added(scratch_engine, row_counts_before, refresh_run)
    with Session(scratch_engine) as session:
        assert (
            session.exec(
                select(Report).where(Report.report_id == _OCTOBER_REPORT_ID)
            ).all()
            == []
        )


def _get_office_table_row_counts(scratch_engine: Engine) -> dict[str, int]:
    with Session(scratch_engine) as session:
        return {
            table.__name__: session.exec(select(func.count()).select_from(table)).one()
            for table in _OFFICE_TABLES
        }


def _seed_ministries(session: Session) -> None:
    session.add_all([Ministry(name=name) for name in get_ministry_names()])
    session.commit()


def _seed_late_office_row(session: Session, sitting_date: date) -> None:
    sitting = Sitting(
        sitting_date=get_sitting_date_key(sitting_date),
        parlement_no=_PREVIOUS_PARLIAMENT_NUMBER,
    )
    session.add(sitting)
    session.flush()
    assert sitting.id is not None
    attendance = Attendance(
        sitting_id=sitting.id, speaker_name=_LATE_SITTING_MEMBER, is_present=True
    )
    session.add(attendance)
    session.flush()
    assert attendance.id is not None
    session.add(
        AttendanceOffice(
            office_printed="Minister for Health",
            entry_line_printed=_LATE_SITTING_ENTRY_LINE,
            office_class=OfficeClass.MINISTER,
            source=AttendanceOfficeSource.AFTER_CONSTITUENCY_BRACKET,
            extracted_at=datetime.now(timezone.utc),
            attendance_id=attendance.id,
        )
    )
    session.commit()


def test_clean_run_stores_the_office_rows_of_the_new_sitting_and_reports(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
) -> None:
    seed_stored(scratch_session)
    _seed_ministries(scratch_session)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    office_table_row_counts = _get_office_table_row_counts(scratch_engine)
    assert office_table_row_counts["AttendanceOffice"] > 0
    assert office_table_row_counts["OfficePrintedRange"] > 0
    assert office_table_row_counts["ReportPutTo"] > 0
    assert office_table_row_counts["OfficeTitleMinistry"] > 0
    new_question_report_ids = {
        search_result["reportId"]
        for search_result in fake_parliament.new_search_results
        if search_result["reportType"] in REPORT_ASKER_REPORT_TYPES
    }
    with Session(scratch_engine) as session:
        put_to_report_ids = set(session.exec(select(ReportPutTo.sprs_report_id)).all())
    assert put_to_report_ids
    assert put_to_report_ids <= new_question_report_ids


def test_database_error_in_the_range_step_leaves_no_office_rows_of_the_month(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    monkeypatch.setattr(
        refresh_runs, "populate_office_printed_ranges", _raise_database_error
    )

    with pytest.raises(SQLAlchemyError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    _assert_failed(scratch_engine, alerts, row_counts_before, "SQLAlchemyError")
    assert set(_get_office_table_row_counts(scratch_engine).values()) == {0}


def test_late_sitting_writes_no_range_and_sends_one_alert(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    _seed_ministries(scratch_session)
    _seed_late_office_row(
        scratch_session, fake_parliament.new_sitting_date + timedelta(days=1)
    )
    attendance_office_count_before = _get_office_table_row_counts(scratch_engine)[
        "AttendanceOffice"
    ]

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    office_table_row_counts = _get_office_table_row_counts(scratch_engine)
    assert office_table_row_counts["OfficePrintedRange"] == 0
    assert office_table_row_counts["AttendanceOffice"] > attendance_office_count_before
    late_sitting_messages = [
        message
        for message in alerts.messages
        if "arrived after a later sitting" in message
    ]
    assert len(late_sitting_messages) == 1
    assert (
        get_sitting_date_key(fake_parliament.new_sitting_date)
        in late_sitting_messages[0]
    )


def test_new_title_with_no_placement_sends_one_alert_and_the_run_succeeds(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
) -> None:
    seed_stored(scratch_session)
    _seed_ministries(scratch_session)
    fake_parliament.new_sitting["attendanceList"][0]["mpName"] = _UNPLACED_ENTRY_LINE

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    unplaced_messages = [
        message for message in alerts.messages if "with no ministry" in message
    ]
    assert len(unplaced_messages) == 1
    assert _UNPLACED_TITLE in unplaced_messages[0]
    with Session(scratch_engine) as session:
        placed_titles = set(
            session.exec(select(OfficeTitleMinistry.office_printed)).all()
        )
    assert _UNPLACED_TITLE not in placed_titles
    _assert_success_pinged(alerts)


def test_office_steps_issue_no_delete_statement(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
) -> None:
    seed_stored(scratch_session)
    _seed_ministries(scratch_session)
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
        status = refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )
    finally:
        event.remove(scratch_engine, "before_cursor_execute", record_statement)

    assert status == RefreshRunStatus.SUCCEEDED
    assert any(
        statement.startswith("INSERT INTO attendance_office")
        for statement in statements
    )
    assert not [statement for statement in statements if statement.startswith("DELETE")]


def test_run_probes_dates_without_a_hit_only_inside_the_recheck_window(
    scratch_session: Session,
    fake_parliament: FakeParliament,
) -> None:
    seed_stored(scratch_session)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_october_now(), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    recheck_start_date = _OCTOBER_RUN_DATE - timedelta(days=_RECHECK_WINDOW_DAYS)
    assert fake_parliament.sitting_calls == [
        get_sitting_date_key(sitting_date)
        for sitting_date in [
            fake_parliament.new_sitting_date,
            *get_dates_between(recheck_start_date, _OCTOBER_RUN_DATE),
        ]
    ]


def test_stored_hit_date_without_a_sitting_is_probed_after_the_recheck_window(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    new_sitting_date_key = get_sitting_date_key(fake_parliament.new_sitting_date)

    def get_unpublished_new_sitting(
        sitting_date: str,
    ) -> Union[HansardReportOldResponse, HansardReportNewResponse]:
        if sitting_date == new_sitting_date_key:
            fake_parliament.sitting_calls.append(sitting_date)
            return HansardReportNewResponse()
        return fake_parliament.get_hansard_report_response(sitting_date)

    monkeypatch.setattr(
        refresh_runs, "get_hansard_report_response", get_unpublished_new_sitting
    )
    refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)
    first_run = _get_only_refresh_run(scratch_engine)
    assert first_run.status == RefreshRunStatus.SUCCEEDED
    assert first_run.reports_added == len(fake_parliament.new_search_results)
    assert first_run.sittings_added == 0
    fake_parliament.sitting_calls.clear()

    refresh_runs.populate_refresh_runs(scratch_session, _get_october_now(), None)

    assert new_sitting_date_key in fake_parliament.sitting_calls


def _set_new_sitting_permission_list(fake_parliament: FakeParliament) -> None:
    fake_parliament.new_sitting["ptbaList"] = [
        {
            "mpName": _LEAVE_MEMBER_NAME,
            "from": "10 Sep",
            "to": "12 Sep",
            "endDtFlag": False,
        },
        {"mpName": None, "from": "10 Sep", "to": "12 Sep", "endDtFlag": False},
    ]


def test_run_stores_the_leave_printings_and_the_seat_rows_of_the_new_sitting(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
) -> None:
    seed_stored(scratch_session)
    _set_new_sitting_permission_list(fake_parliament)

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    with Session(scratch_engine) as session:
        printings = session.exec(
            select(LeavePeriodPrinting).order_by(col(LeavePeriodPrinting.ordinal))
        ).all()
        assert [
            (printing.printed_name, printing.carried_name) for printing in printings
        ] == [(_LEAVE_MEMBER_NAME, None), (None, _LEAVE_MEMBER_NAME)]
        assert {printing.office_printed for printing in printings} == {
            _LEAVE_MEMBER_OFFICE
        }
        assert len(session.exec(select(LeavePeriod)).all()) == 1
        new_sitting_speaker_ids = {
            attendance.speaker_id
            for attendance in session.exec(
                select(Attendance)
                .join(Sitting, col(Sitting.id) == col(Attendance.sitting_id))
                .where(Sitting.sitting_date == _NEW_SITTING_DATE_KEY)
            ).all()
            if attendance.speaker_id is not None
        }
        seat_holdings = session.exec(select(SeatHolding)).all()
        assert seat_holdings != []
        assert {seat_holding.speaker_id for seat_holding in seat_holdings} <= (
            new_sitting_speaker_ids
        )


@dataclass
class _StatementRecorder:
    statements: list[str] = field(default_factory=list)

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


def _seed_earlier_seat_holding(session: Session) -> None:
    chee = session.exec(
        select(Speaker)
        .where(Speaker.name == _LEAVE_MEMBER_SPEAKER_NAME)
        .where(Speaker.parliament_number == _PREVIOUS_PARLIAMENT_NUMBER)
    ).one()
    assert chee.id is not None
    session.add(
        SeatHolding(
            division_key=_LEAVE_MEMBER_DIVISION_KEY,
            location_name=_LEAVE_MEMBER_DIVISION,
            first_sitting_date=_EARLIER_SEAT_DATE,
            last_sitting_date=_EARLIER_SEAT_DATE,
            sitting_count=1,
            speaker_id=chee.id,
        )
    )
    session.commit()


def test_run_issues_no_delete_and_updates_only_the_three_seat_bounds(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
) -> None:
    seed_stored(scratch_session)
    _seed_earlier_seat_holding(scratch_session)
    _set_new_sitting_permission_list(fake_parliament)
    statement_recorder = _StatementRecorder()
    event.listen(
        scratch_engine, "before_cursor_execute", statement_recorder.record_statement
    )

    try:
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )
    finally:
        event.remove(
            scratch_engine, "before_cursor_execute", statement_recorder.record_statement
        )

    assert not [
        statement
        for statement in statement_recorder.statements
        if statement.lstrip().upper().startswith("DELETE")
    ]
    seat_updates = [
        statement
        for statement in statement_recorder.statements
        if statement.startswith("UPDATE seat_holding")
    ]
    assert seat_updates != []
    for seat_update in seat_updates:
        set_clause = seat_update.partition(" SET ")[2].partition(" WHERE ")[0]
        assert {
            assignment.partition("=")[0].strip()
            for assignment in set_clause.split(", ")
        } == set(_SEAT_UPDATE_COLUMNS)
    with Session(scratch_engine) as session:
        widened = session.exec(
            select(SeatHolding).where(
                SeatHolding.division_key == _LEAVE_MEMBER_DIVISION_KEY,
                SeatHolding.first_sitting_date == _EARLIER_SEAT_DATE,
            )
        ).one()
        assert widened.last_sitting_date == fake_parliament.new_sitting_date


def test_a_second_run_leaves_the_same_leave_and_seat_rows(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
) -> None:
    seed_stored(scratch_session)
    _set_new_sitting_permission_list(fake_parliament)
    refresh_runs.populate_refresh_runs(scratch_session, _get_now(fake_parliament), None)
    with Session(scratch_engine) as session:
        printings_after_first_run = session.exec(select(LeavePeriodPrinting)).all()
        seat_holdings_after_first_run = session.exec(select(SeatHolding)).all()
        printing_values = sorted(
            printing.model_dump().items() for printing in printings_after_first_run
        )
        seat_holding_values = sorted(
            seat_holding.model_dump().items()
            for seat_holding in seat_holdings_after_first_run
        )

    status = refresh_runs.populate_refresh_runs(
        scratch_session, _get_now(fake_parliament), None
    )

    assert status == RefreshRunStatus.SUCCEEDED
    with Session(scratch_engine) as session:
        assert (
            sorted(
                printing.model_dump().items()
                for printing in session.exec(select(LeavePeriodPrinting)).all()
            )
            == printing_values
        )
        assert (
            sorted(
                seat_holding.model_dump().items()
                for seat_holding in session.exec(select(SeatHolding)).all()
            )
            == seat_holding_values
        )


def test_a_failing_seat_step_rolls_the_month_back_and_leaves_no_printing(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
    alerts: _AlertRecorder,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_stored(scratch_session)
    row_counts_before = _get_row_counts(scratch_engine)
    _set_new_sitting_permission_list(fake_parliament)
    monkeypatch.setattr(refresh_runs, "populate_seat_holdings", _raise_database_error)

    with pytest.raises(SQLAlchemyError):
        refresh_runs.populate_refresh_runs(
            scratch_session, _get_now(fake_parliament), None
        )

    _assert_failed(scratch_engine, alerts, row_counts_before, "SQLAlchemyError")
    with Session(scratch_engine) as session:
        assert session.exec(select(LeavePeriodPrinting)).all() == []
        assert session.exec(select(LeavePeriod)).all() == []
        assert session.exec(select(SeatHolding)).all() == []
