import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Union

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from crud.attendance import CRUDAttendance
from crud.hansard_sitting_date_response import CRUDHansardSittingDateResponse
from crud.hansard_website_response import CRUDHansardWebsiteResponse
from crud.refresh_run import CRUDRefreshRun
from crud.report import CRUDReport
from crud.sitting import CRUDSitting
from crud.speaker import CRUDSpeaker
from crud.speech import CRUDSpeech
from database.attendance import Attendance
from database.refresh_run import RefreshRun
from database.report import Report
from database.sitting import Sitting
from database.speech import Speech
from enums import RefreshRunStatus, ReportType
from exceptions import (
    HansardError,
    HansardGatewayError,
    HansardRefreshFailureError,
    HansardRefreshHaltError,
    HansardRefreshRunError,
)
from gateway.hansard_report import get_hansard_report_response
from gateway.hansard_search import get_all_hansard_search_results
from gateway.hansard_topic import get_hansard_topic_response_async
from gateway.healthchecks import send_healthchecks_failure_ping, send_healthchecks_ping
from gateway.telegram import send_telegram_message
from logs import logger
from populate.attribution_figures import get_attribution_figures
from populate.speaker_links import link_speakers_by_report_ids_and_sitting_ids
from schemas.hansard_report_response import (
    HansardReportNewResponse,
    HansardReportOldResponse,
)
from schemas.hansard_search_result import HansardSearchResult
from schemas.hansard_topic_response import HansardTopicResponse
from services.api_field_mapping import (
    get_search_result_field_losses,
    get_sitting_date_field_losses,
    get_topic_field_losses,
)
from services.attendance import (
    build_constituency_lookups,
    build_sitting_attendances,
    build_speaker_lookups,
)
from services.attribution import (
    LINKED_CATEGORY,
    NAMED_UNLINKED_CATEGORY,
    build_attribution_figures_json,
    get_speech_category,
)
from services.hansard_sitting_date_response import build_hansard_sitting_date_response
from services.hansard_website import (
    build_hansard_website_response,
    get_topic_html_content,
    get_topic_id,
)
from services.refresh import (
    build_changed_report_message,
    build_error_bodies_reason,
    build_failure_message,
    build_field_mapping_reason,
    build_halt_message,
    build_held_report_message,
    build_many_held_reports_message,
    build_new_parliament_reason,
    build_summary_message,
    build_unlinked_labels_message,
    build_unlinked_reason,
    get_content_hash,
    get_dates_between,
    get_probe_start_date,
    get_recheck_start_date,
    get_singapore_today,
    get_telegram_text,
    get_unexpected_parliament_numbers,
    get_unlinked_share,
    is_every_topic_an_error_body,
    is_held_report_alert_due,
    is_held_report_count_over_limit,
    is_published_sitting_response,
    is_unlinked_share_over_limit,
)
from services.report import build_report
from services.sitting import build_sitting
from services.speech import ReportSkipReason, build_report_speeches
from settings import settings
from utils.data_files import (
    get_constituency_names,
    get_excluded_report_ids,
    get_unattributed_speech_ranges,
)
from utils.json_columns import get_json_column
from utils.sitting_dates import (
    MonthWindow,
    get_month_windows,
    get_sitting_date_key,
    parse_sitting_date,
)

_STALE_RUN_HOURS = 12
_MAX_FAILURE_REASON_LENGTH = 1_000
_HTTP_TIMEOUT_SECONDS = 60
_AFTER_DATA_COMMIT = "After the data commit: "


@dataclass(frozen=True)
class TopicRequest:
    report_id: str
    html_file_name: Optional[str]
    report_version: str


@dataclass(frozen=True)
class FetchedTopic:
    hansard_topic_response: HansardTopicResponse
    html_content: Optional[str]


@dataclass(frozen=True)
class StoredRefreshState:
    stored_sitting_dates: set[date]
    stored_report_ids: set[str]
    excluded_report_ids: set[str]
    stored_parliament_maximum: Optional[int]
    recheck_topic_requests: list[TopicRequest]
    report_id_to_stored_content: dict[str, str]
    report_id_to_stored_sitting_date: dict[str, str]


@dataclass(frozen=True)
class FetchedWindow:
    new_search_results: list[HansardSearchResult]
    report_id_to_fetched_topic: dict[str, FetchedTopic]
    sitting_date_key_to_response: dict[str, Union[HansardReportOldResponse, HansardReportNewResponse]]
    stored_parliament_maximum: Optional[int]


@dataclass(frozen=True)
class NewRowIds:
    report_ids: list[int]
    sitting_ids: list[int]
    website_report_ids: list[str]
    sitting_dates: list[date]


@dataclass(frozen=True)
class NewRowCounts:
    linked_row_count: int
    named_unlinked_row_count: int
    label_to_row_count: dict[str, int]


@dataclass(frozen=True)
class ChangedReport:
    report_id: str
    sitting_date: str


@dataclass(frozen=True)
class HeldReport:
    report_id: str
    sitting_date: str


@dataclass
class RunResult:
    website_responses_added: int = 0
    sitting_date_responses_added: int = 0
    sittings_added: int = 0
    reports_added: int = 0
    speeches_added: int = 0
    speeches_linked: int = 0
    speeches_named_unlinked: int = 0
    attendances_added: int = 0
    attendances_linked: int = 0
    reports_held_without_text: int = 0
    topics_fetched: int = 0
    topics_with_error_body: int = 0
    reports_without_speech_rows: int = 0
    reports_rechecked: int = 0
    reports_changed: int = 0
    latest_sitting_date_with_text: Optional[date] = None
    figures: Optional[dict[str, object]] = None
    changed_reports: list[ChangedReport] = field(default_factory=list)
    held_reports_to_alert: list[HeldReport] = field(default_factory=list)
    label_to_row_count: dict[str, int] = field(default_factory=dict)


def _send_alert(text: str) -> None:
    if settings.telegram_bot_token is None:
        return
    if settings.telegram_chat_id is None:
        return
    try:
        send_telegram_message(settings.telegram_bot_token, settings.telegram_chat_id, get_telegram_text(text))
    except HansardGatewayError as error:
        logger.warning(f"Alert not sent: {error}")


def _send_success_ping() -> None:
    if settings.healthchecks_ping_url is None:
        return
    try:
        send_healthchecks_ping(settings.healthchecks_ping_url)
    except HansardGatewayError as error:
        logger.warning(f"Ping not sent: {error}")


def _send_failure_ping() -> None:
    if settings.healthchecks_ping_url is None:
        return
    try:
        send_healthchecks_failure_ping(settings.healthchecks_ping_url)
    except HansardGatewayError as error:
        logger.warning(f"Failure ping not sent: {error}")


def _get_alert_failure_reason(error: Exception, is_data_committed: bool) -> str:
    error_text = f"{type(error).__name__}: {error}" if isinstance(error, HansardError) else type(error).__name__
    if is_data_committed:
        return f"{error_text} after the data commit"
    return error_text


def _insert_refresh_run(session: Session, now: datetime) -> int:
    stale_run_ids = [
        refresh_run.id
        for refresh_run in CRUDRefreshRun(session).get_by_status_and_started_at_before(RefreshRunStatus.RUNNING, now - timedelta(hours=_STALE_RUN_HOURS))
        if refresh_run.id is not None
    ]
    for stale_run_id in stale_run_ids:
        stale_run = CRUDRefreshRun(session).get_by_id_for_update(stale_run_id)
        if stale_run is None:
            session.rollback()
            continue
        if stale_run.status != RefreshRunStatus.RUNNING:
            session.rollback()
            continue
        stale_run.status = RefreshRunStatus.FAILED
        stale_run.failure_reason = "Run ended without finishing"
        stale_run.finished_at = datetime.now(timezone.utc)
        CRUDRefreshRun(session).update(stale_run)
    refresh_run = RefreshRun(started_at=now)
    CRUDRefreshRun(session).create(refresh_run)
    if refresh_run.id is None:
        raise HansardRefreshRunError("Run row has no id after commit")
    return refresh_run.id


def _start_refresh_run(session: Session, now: datetime) -> int:
    try:
        return _insert_refresh_run(session, now)
    except Exception as error:  # noqa: BLE001 a run that cannot start still alerts and pings before the error propagates
        logger.error(f"Refresh run could not start: {type(error).__name__}")
        _send_alert(build_failure_message(_get_alert_failure_reason(error, False)))
        _send_failure_ping()
        raise


def _validate_can_run(session: Session, refresh_run_id: int, now: datetime) -> None:
    for refresh_run in CRUDRefreshRun(session).get_by_status_and_started_at_from(RefreshRunStatus.RUNNING, now - timedelta(hours=_STALE_RUN_HOURS)):
        if refresh_run.id != refresh_run_id:
            raise HansardRefreshRunError("Another run is in progress")


async def _fetch_topics(topic_requests: list[TopicRequest]) -> dict[str, FetchedTopic]:
    report_id_to_fetched_topic: dict[str, FetchedTopic] = {}
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        for topic_request in topic_requests:
            hansard_topic_response = await get_hansard_topic_response_async(
                get_topic_id(topic_request.report_id, topic_request.html_file_name, topic_request.report_version),
                client,
            )
            html_content = get_topic_html_content(hansard_topic_response, topic_request.report_version)
            report_id_to_fetched_topic[topic_request.report_id] = FetchedTopic(hansard_topic_response, html_content)
    return report_id_to_fetched_topic


def _fetch_sitting_responses(
    sitting_dates: list[date],
    sitting_dates_with_search_results: set[date],
) -> dict[str, Union[HansardReportOldResponse, HansardReportNewResponse]]:
    sitting_date_key_to_response: dict[str, Union[HansardReportOldResponse, HansardReportNewResponse]] = {}
    for sitting_date in sitting_dates:
        sitting_date_key = get_sitting_date_key(sitting_date)
        try:
            hansard_report_response = get_hansard_report_response(sitting_date_key)
        except HansardGatewayError as error:
            if sitting_date in sitting_dates_with_search_results:
                raise
            logger.info(f"No sitting response for {sitting_date}: {error}")
            continue
        if is_published_sitting_response(hansard_report_response):
            sitting_date_key_to_response[sitting_date_key] = hansard_report_response
    return sitting_date_key_to_response


def _get_stored_parliament_maximum(session: Session) -> Optional[int]:
    stored_maximums = (CRUDReport(session).get_max_parliament_number(), CRUDSitting(session).get_max_parlement_no())
    return max((stored_maximum for stored_maximum in stored_maximums if stored_maximum is not None), default=None)


def _validate_can_accept_parliament_numbers(
    parliament_numbers: set[int],
    stored_maximum: Optional[int],
    allowed_parliament_number: Optional[int],
) -> None:
    unexpected_parliament_numbers = get_unexpected_parliament_numbers(parliament_numbers, stored_maximum, allowed_parliament_number)
    if unexpected_parliament_numbers:
        raise HansardRefreshHaltError(build_new_parliament_reason(unexpected_parliament_numbers))


def _load_stored_refresh_state(session: Session, today: date) -> StoredRefreshState:
    stored_sitting_dates = {
        parse_sitting_date(sitting_date_key).date()
        for sitting_date_key in CRUDHansardSittingDateResponse(session).get_sitting_dates_by_sitting_date_not_null()
    }
    if not stored_sitting_dates:
        raise HansardRefreshRunError("No stored sitting to start from")
    stored_report_ids = CRUDHansardWebsiteResponse(session).get_all_report_ids()
    excluded_report_ids = {excluded_report_id.report_id for excluded_report_id in get_excluded_report_ids()}
    stored_parliament_maximum = _get_stored_parliament_maximum(session)
    recheck_report_ids = CRUDReport(session).get_report_ids_by_sitting_date_from(datetime.combine(get_recheck_start_date(today), time.min))
    recheck_topic_requests = []
    report_id_to_stored_content: dict[str, str] = {}
    report_id_to_stored_sitting_date: dict[str, str] = {}
    for hansard_website_response in CRUDHansardWebsiteResponse(session).get_by_report_ids(recheck_report_ids):
        stored_content = hansard_website_response.content
        if stored_content is None or stored_content == "":
            continue
        if hansard_website_response.report_id in report_id_to_stored_content:
            continue
        recheck_topic_requests.append(
            TopicRequest(hansard_website_response.report_id, hansard_website_response.html_file_name, hansard_website_response.report_version)
        )
        report_id_to_stored_content[hansard_website_response.report_id] = stored_content
        report_id_to_stored_sitting_date[hansard_website_response.report_id] = hansard_website_response.sitting_date
    # NOTE: nothing is pending; the commit ends the read transaction so none stays open through the crawl
    session.commit()
    return StoredRefreshState(
        stored_sitting_dates,
        stored_report_ids,
        excluded_report_ids,
        stored_parliament_maximum,
        recheck_topic_requests,
        report_id_to_stored_content,
        report_id_to_stored_sitting_date,
    )


def _get_changed_reports(
    report_id_to_rechecked_topic: dict[str, FetchedTopic],
    stored_refresh_state: StoredRefreshState,
) -> list[ChangedReport]:
    changed_reports = []
    for report_id, rechecked_topic in report_id_to_rechecked_topic.items():
        html_content = rechecked_topic.html_content
        if html_content is None or html_content == "":
            logger.info(f"Re-check of {report_id} returned no text")
            continue
        if get_content_hash(stored_refresh_state.report_id_to_stored_content[report_id]) != get_content_hash(html_content):
            changed_reports.append(ChangedReport(report_id, stored_refresh_state.report_id_to_stored_sitting_date[report_id]))
    return changed_reports


def _fetch_changed_reports(stored_refresh_state: StoredRefreshState, run_result: RunResult) -> list[ChangedReport]:
    report_id_to_rechecked_topic = asyncio.run(_fetch_topics(stored_refresh_state.recheck_topic_requests))
    run_result.topics_fetched += len(report_id_to_rechecked_topic)
    run_result.topics_with_error_body += sum(1 for rechecked_topic in report_id_to_rechecked_topic.values() if rechecked_topic.html_content is None)
    field_losses = []
    for rechecked_topic in report_id_to_rechecked_topic.values():
        field_losses.extend(get_topic_field_losses(rechecked_topic.hansard_topic_response, rechecked_topic.html_content))
    if field_losses:
        raise HansardRefreshHaltError(build_field_mapping_reason(field_losses))
    return _get_changed_reports(report_id_to_rechecked_topic, stored_refresh_state)


def _fetch_window(
    stored_refresh_state: StoredRefreshState,
    month_window: MonthWindow,
    allowed_parliament_number: Optional[int],
) -> FetchedWindow:
    # NOTE: the search can return one hit twice, so keep the first hit per report_id.
    report_id_to_first_search_result: dict[str, HansardSearchResult] = {}
    for search_result in get_all_hansard_search_results(month_window.first_date, month_window.last_date):
        report_id_to_first_search_result.setdefault(search_result.report_id, search_result)
    new_search_results = [
        search_result
        for search_result in report_id_to_first_search_result.values()
        if search_result.report_id not in stored_refresh_state.stored_report_ids
        and search_result.report_id not in stored_refresh_state.excluded_report_ids
    ]
    _validate_can_accept_parliament_numbers(
        {int(search_result.parl_no) for search_result in new_search_results},
        stored_refresh_state.stored_parliament_maximum,
        allowed_parliament_number,
    )
    report_id_to_fetched_topic = asyncio.run(_fetch_topics([
        TopicRequest(search_result.report_id, search_result.html_file_name, search_result.report_version)
        for search_result in new_search_results
    ]))
    sitting_dates_with_search_results = {parse_sitting_date(search_result.sitting_date).date() for search_result in new_search_results}
    sitting_dates_to_probe = [
        sitting_date
        for sitting_date in get_dates_between(month_window.first_date, month_window.last_date)
        if sitting_date not in stored_refresh_state.stored_sitting_dates
    ]
    sitting_date_key_to_response = _fetch_sitting_responses(sitting_dates_to_probe, sitting_dates_with_search_results)
    return FetchedWindow(
        new_search_results,
        report_id_to_fetched_topic,
        sitting_date_key_to_response,
        stored_refresh_state.stored_parliament_maximum,
    )


def _validate_can_store_fetched_window(fetched_window: FetchedWindow, allowed_parliament_number: Optional[int]) -> None:
    field_losses = []
    for search_result in fetched_window.new_search_results:
        html_content = fetched_window.report_id_to_fetched_topic[search_result.report_id].html_content
        field_losses.extend(get_search_result_field_losses(search_result, build_hansard_website_response(search_result, html_content)))
    for fetched_topic in fetched_window.report_id_to_fetched_topic.values():
        field_losses.extend(get_topic_field_losses(fetched_topic.hansard_topic_response, fetched_topic.html_content))
    sitting_parliament_numbers = set()
    for sitting_date_key, hansard_report_response in fetched_window.sitting_date_key_to_response.items():
        hansard_sitting_date_response = build_hansard_sitting_date_response(hansard_report_response, sitting_date_key)
        if isinstance(hansard_report_response, HansardReportNewResponse):
            if hansard_report_response.metadata is not None and hansard_report_response.metadata.parliment_no is not None:
                sitting_parliament_numbers.add(hansard_report_response.metadata.parliment_no)
        elif hansard_report_response.parl_no is not None:
            sitting_parliament_numbers.add(int(str(hansard_report_response.parl_no)))
        field_losses.extend(get_sitting_date_field_losses(hansard_report_response, hansard_sitting_date_response))
    if field_losses:
        raise HansardRefreshHaltError(build_field_mapping_reason(field_losses))
    _validate_can_accept_parliament_numbers(sitting_parliament_numbers, fetched_window.stored_parliament_maximum, allowed_parliament_number)


def _set_sitting_detail_columns(sitting: Sitting, hansard_report_response: HansardReportNewResponse) -> None:
    sitting.sections = get_json_column(hansard_report_response.takes_section_vo_list)
    sitting.annexures = get_json_column(hansard_report_response.annexure_list)
    sitting.vernaculars = get_json_column(hansard_report_response.vernacular_list)
    sitting.a2b = get_json_column(hansard_report_response.a2b_list)


def _write_window_rows(session: Session, fetched_window: FetchedWindow, window_result: RunResult, today: date) -> NewRowIds:
    hansard_website_responses = []
    website_report_ids = []
    for search_result in fetched_window.new_search_results:
        html_content = fetched_window.report_id_to_fetched_topic[search_result.report_id].html_content
        if search_result.report_type != ReportType.ATBP:
            window_result.topics_fetched += 1
            if html_content is None:
                window_result.topics_with_error_body += 1
        if (html_content is not None and html_content != "") or search_result.report_type == ReportType.ATBP:
            hansard_website_responses.append(build_hansard_website_response(search_result, html_content))
            website_report_ids.append(search_result.report_id)
            continue
        window_result.reports_held_without_text += 1
        if is_held_report_alert_due(parse_sitting_date(search_result.sitting_date).date(), today):
            window_result.held_reports_to_alert.append(HeldReport(search_result.report_id, search_result.sitting_date))
    CRUDHansardWebsiteResponse(session).add_many(hansard_website_responses)

    reports = [build_report(hansard_website_response) for hansard_website_response in hansard_website_responses]
    CRUDReport(session).add_many(reports)

    report_id_to_unattributed_range = {speech_range.report_id: speech_range for speech_range in get_unattributed_speech_ranges()}
    speeches = []
    for report in reports:
        report_speeches = build_report_speeches(report, report_id_to_unattributed_range)
        if report_speeches.skip_reason == ReportSkipReason.NO_MARKDOWN_CONTENT:
            logger.debug(f"Skipping report {report.id}: no markdown content")
        if report_speeches.skip_reason == ReportSkipReason.NO_START_OF_SPEECH_LINE:
            logger.debug(f"Skipping report {report.id}: could not find start of speech line")
        if not report_speeches.speeches:
            window_result.reports_without_speech_rows += 1
        speeches.extend(report_speeches.speeches)
    CRUDSpeech(session).add_many(speeches)

    hansard_sitting_date_responses = []
    sittings = []
    for sitting_date_key, hansard_report_response in fetched_window.sitting_date_key_to_response.items():
        hansard_sitting_date_response = build_hansard_sitting_date_response(hansard_report_response, sitting_date_key)
        sitting = build_sitting(hansard_sitting_date_response)
        if isinstance(hansard_report_response, HansardReportNewResponse):
            _set_sitting_detail_columns(sitting, hansard_report_response)
        hansard_sitting_date_responses.append(hansard_sitting_date_response)
        sittings.append(sitting)
    CRUDHansardSittingDateResponse(session).add_many(hansard_sitting_date_responses)
    CRUDSitting(session).add_many(sittings)

    lookups = build_speaker_lookups(CRUDSpeaker(session).get_all())
    constituency_lookups = build_constituency_lookups(get_constituency_names())
    attendances = [
        attendance for sitting in sittings for attendance in build_sitting_attendances(sitting, lookups, constituency_lookups)
    ]
    CRUDAttendance(session).add_many(attendances)

    report_ids = [report.id for report in reports if report.id is not None]
    sitting_ids = [sitting.id for sitting in sittings if sitting.id is not None]
    link_speakers_by_report_ids_and_sitting_ids(session, report_ids, sitting_ids)

    window_result.website_responses_added = len(hansard_website_responses)
    window_result.reports_added = len(reports)
    window_result.speeches_added = len(speeches)
    window_result.sitting_date_responses_added = len(hansard_sitting_date_responses)
    window_result.sittings_added = len(sittings)
    window_result.attendances_added = len(attendances)
    window_result.attendances_linked = CRUDAttendance(session).get_count_by_sitting_ids_and_speaker_id_not_null(sitting_ids)
    sitting_dates = [parse_sitting_date(sitting_date_key).date() for sitting_date_key in fetched_window.sitting_date_key_to_response]
    return NewRowIds(report_ids, sitting_ids, website_report_ids, sitting_dates)


def _get_new_row_counts(session: Session, report_ids: list[int]) -> NewRowCounts:
    category_to_row_count: Counter[str] = Counter()
    label_to_row_count: Counter[str] = Counter()
    for speech_row in CRUDSpeech(session).get_rows_by_report_ids(report_ids):
        category = get_speech_category(speech_row.speaker, speech_row.speaker_id)
        category_to_row_count[category] += 1
        if category == NAMED_UNLINKED_CATEGORY and speech_row.speaker is not None:
            label_to_row_count[speech_row.speaker] += 1
    return NewRowCounts(category_to_row_count[LINKED_CATEGORY], category_to_row_count[NAMED_UNLINKED_CATEGORY], dict(label_to_row_count))


def _get_table_name_to_vacuum_count(session: Session) -> dict[str, int]:
    return {
        Speech.__tablename__: CRUDSpeech(session).get_vacuum_count(),
        Report.__tablename__: CRUDReport(session).get_vacuum_count(),
        Attendance.__tablename__: CRUDAttendance(session).get_vacuum_count(),
    }


def _vacuum_analyze_tables(session: Session) -> None:
    table_name_to_vacuum_count = _get_table_name_to_vacuum_count(session)
    # NOTE: nothing is pending; the commit ends the read transaction, which VACUUM cannot run inside
    session.commit()
    CRUDSpeech(session).vacuum_analyze()
    CRUDReport(session).vacuum_analyze()
    CRUDAttendance(session).vacuum_analyze()
    for table_name, vacuum_count in _get_table_name_to_vacuum_count(session).items():
        if vacuum_count == table_name_to_vacuum_count[table_name]:
            raise HansardRefreshRunError(f"VACUUM (ANALYZE) did not run on {table_name}; Postgres skips a table the role cannot MAINTAIN")


def _finish_refresh_run(
    session: Session,
    refresh_run_id: int,
    run_result: RunResult,
    status: RefreshRunStatus,
    halt_reason: Optional[str],
    failure_reason: Optional[str],
) -> None:
    stored_run = CRUDRefreshRun(session).get_by_id_for_update(refresh_run_id)
    if stored_run is None:
        raise HansardRefreshRunError(f"Run {refresh_run_id} is not stored")
    if stored_run.status != RefreshRunStatus.RUNNING:
        raise HansardRefreshRunError(f"Run {refresh_run_id} is already {stored_run.status}")
    stored_run.website_responses_added = run_result.website_responses_added
    stored_run.sitting_date_responses_added = run_result.sitting_date_responses_added
    stored_run.sittings_added = run_result.sittings_added
    stored_run.reports_added = run_result.reports_added
    stored_run.speeches_added = run_result.speeches_added
    stored_run.speeches_linked = run_result.speeches_linked
    stored_run.speeches_named_unlinked = run_result.speeches_named_unlinked
    stored_run.attendances_added = run_result.attendances_added
    stored_run.attendances_linked = run_result.attendances_linked
    stored_run.reports_held_without_text = run_result.reports_held_without_text
    stored_run.reports_without_speech_rows = run_result.reports_without_speech_rows
    stored_run.reports_rechecked = run_result.reports_rechecked
    stored_run.reports_changed = run_result.reports_changed
    stored_run.latest_sitting_date_with_text = run_result.latest_sitting_date_with_text
    stored_run.figures = run_result.figures
    stored_run.status = status
    stored_run.finished_at = datetime.now(timezone.utc)
    stored_run.halt_reason = halt_reason
    stored_run.failure_reason = failure_reason
    CRUDRefreshRun(session).update(stored_run)


def _record_finish(
    session: Session,
    refresh_run_id: int,
    run_result: RunResult,
    status: RefreshRunStatus,
    halt_reason: Optional[str],
    failure_reason: Optional[str],
) -> None:
    try:
        session.rollback()
        _finish_refresh_run(session, refresh_run_id, run_result, status, halt_reason, failure_reason)
    except SQLAlchemyError as error:
        logger.error(f"Run {refresh_run_id} not recorded: {type(error).__name__}")
    except HansardRefreshRunError as error:
        logger.error(f"Run {refresh_run_id} not recorded: {error}")


def _add_window_result(run_result: RunResult, window_result: RunResult) -> None:
    run_result.website_responses_added += window_result.website_responses_added
    run_result.sitting_date_responses_added += window_result.sitting_date_responses_added
    run_result.sittings_added += window_result.sittings_added
    run_result.reports_added += window_result.reports_added
    run_result.speeches_added += window_result.speeches_added
    run_result.speeches_linked += window_result.speeches_linked
    run_result.speeches_named_unlinked += window_result.speeches_named_unlinked
    run_result.attendances_added += window_result.attendances_added
    run_result.attendances_linked += window_result.attendances_linked
    run_result.reports_held_without_text += window_result.reports_held_without_text
    run_result.topics_fetched += window_result.topics_fetched
    run_result.topics_with_error_body += window_result.topics_with_error_body
    run_result.reports_without_speech_rows += window_result.reports_without_speech_rows
    run_result.held_reports_to_alert.extend(window_result.held_reports_to_alert)
    for label, row_count in window_result.label_to_row_count.items():
        run_result.label_to_row_count[label] = run_result.label_to_row_count.get(label, 0) + row_count


def _send_success_alerts(run_result: RunResult) -> None:
    for changed_report in run_result.changed_reports:
        _send_alert(build_changed_report_message(changed_report.report_id, changed_report.sitting_date))
    if run_result.label_to_row_count:
        _send_alert(build_unlinked_labels_message(run_result.label_to_row_count))
    for held_report in run_result.held_reports_to_alert:
        _send_alert(build_held_report_message(held_report.report_id, held_report.sitting_date))
    if is_held_report_count_over_limit(run_result.reports_held_without_text):
        _send_alert(build_many_held_reports_message(run_result.reports_held_without_text))
    if run_result.website_responses_added + run_result.sitting_date_responses_added > 0:
        unlinked_share = get_unlinked_share(run_result.speeches_linked, run_result.speeches_named_unlinked)
        linked_share = None if unlinked_share is None else 1 - unlinked_share
        _send_alert(build_summary_message(run_result.sittings_added, run_result.reports_added, run_result.speeches_added, linked_share))


def _record_failure(
    session: Session,
    refresh_run_id: int,
    run_result: RunResult,
    error: Exception,
    is_data_committed: bool,
    is_run_finished: bool,
) -> None:
    if is_run_finished:
        logger.error(f"Run {refresh_run_id} failed after it was recorded as succeeded")
        return
    error_text = f"{type(error).__name__}: {error}"
    failure_reason = f"{_AFTER_DATA_COMMIT}{error_text}" if is_data_committed else error_text
    _record_finish(
        session,
        refresh_run_id,
        run_result,
        RefreshRunStatus.FAILED,
        None,
        failure_reason[:_MAX_FAILURE_REASON_LENGTH],
    )


def populate_refresh_runs(session: Session, now: datetime, allowed_parliament_number: Optional[int]) -> RefreshRunStatus:
    refresh_run_id = _start_refresh_run(session, now)
    today = get_singapore_today(now)
    run_result = RunResult()
    is_data_committed = False
    is_run_finished = False
    try:
        _validate_can_run(session, refresh_run_id, now)
        stored_refresh_state = _load_stored_refresh_state(session, today)
        run_result.changed_reports = _fetch_changed_reports(stored_refresh_state, run_result)
        run_result.reports_changed = len(run_result.changed_reports)
        run_result.reports_rechecked = len(stored_refresh_state.recheck_topic_requests)
        probe_start_date = get_probe_start_date(max(stored_refresh_state.stored_sitting_dates), today)
        for month_window in get_month_windows(probe_start_date, today):
            window_result = RunResult()
            fetched_window = _fetch_window(stored_refresh_state, month_window, allowed_parliament_number)
            _validate_can_store_fetched_window(fetched_window, allowed_parliament_number)
            new_row_ids = _write_window_rows(session, fetched_window, window_result, today)
            new_row_counts = _get_new_row_counts(session, new_row_ids.report_ids)
            window_result.speeches_linked = new_row_counts.linked_row_count
            window_result.speeches_named_unlinked = new_row_counts.named_unlinked_row_count
            window_result.label_to_row_count = new_row_counts.label_to_row_count
            unlinked_share = get_unlinked_share(new_row_counts.linked_row_count, new_row_counts.named_unlinked_row_count)
            if unlinked_share is not None and is_unlinked_share_over_limit(unlinked_share):
                raise HansardRefreshHaltError(build_unlinked_reason(unlinked_share, new_row_counts.label_to_row_count))
            session.commit()
            stored_refresh_state.stored_report_ids.update(new_row_ids.website_report_ids)
            stored_refresh_state.stored_sitting_dates.update(new_row_ids.sitting_dates)
            _add_window_result(run_result, window_result)
            is_data_committed = run_result.website_responses_added + run_result.sitting_date_responses_added > 0
        if is_every_topic_an_error_body(run_result.topics_fetched, run_result.topics_with_error_body):
            raise HansardRefreshFailureError(build_error_bodies_reason(run_result.topics_fetched))
        run_result.figures = build_attribution_figures_json(get_attribution_figures(session), datetime.now(timezone.utc))
        latest_sitting_date = CRUDReport(session).get_max_sitting_date_by_content_not_null_and_content_not_empty()
        run_result.latest_sitting_date_with_text = None if latest_sitting_date is None else latest_sitting_date.date()
        _vacuum_analyze_tables(session)
        _finish_refresh_run(session, refresh_run_id, run_result, RefreshRunStatus.SUCCEEDED, None, None)
        is_run_finished = True
        _send_success_alerts(run_result)
        _send_success_ping()
        return RefreshRunStatus.SUCCEEDED
    except HansardRefreshHaltError as error:
        _record_finish(session, refresh_run_id, run_result, RefreshRunStatus.HALTED, str(error), None)
        _send_alert(build_halt_message(str(error)))
        if is_data_committed:
            _send_success_alerts(run_result)
        _send_failure_ping()
        return RefreshRunStatus.HALTED
    except Exception as unexpected_failure:  # noqa: BLE001 a failed run is recorded, alerted and pinged before the error propagates
        _record_failure(session, refresh_run_id, run_result, unexpected_failure, is_data_committed, is_run_finished)
        _send_alert(build_failure_message(_get_alert_failure_reason(unexpected_failure, is_data_committed)))
        if is_data_committed and not is_run_finished:
            _send_success_alerts(run_result)
        _send_failure_ping()
        raise
