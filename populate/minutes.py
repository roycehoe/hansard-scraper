import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Optional

from sqlmodel import Session

from crud.division import CRUDDivision
from crud.minutes import CRUDMinutes
from crud.minutes_index_capture import CRUDMinutesIndexCapture
from crud.report import CRUDReport
from database.minutes import Minutes, MinutesIndexCapture
from enums import MinutesFileFormat, MinutesIndexSource, MinutesStatus
from exceptions import (
    HansardGatewayError,
    HansardMinutesFileError,
    HansardMinutesIndexError,
    HansardMinutesIndexUnavailableError,
)
from gateway.minutes import get_minutes_file_response, get_minutes_index_response
from logs import logger
from populate.division_party_counts import populate_division_party_counts
from populate.minutes_divisions import populate_minutes_divisions
from schemas.minutes_response import MinutesResponse
from services.minutes_index import (
    MINUTES_INDEX_FIRST_DATE,
    MinutesIndexRow,
    get_live_capture_url,
    parse_live_index_page,
)
from services.minutes_text import (
    get_minutes_file_format,
    get_minutes_pdf_text,
    get_minutes_text_outcome,
)
from settings import settings

_HTTP_OK = 200
_REQUEST_FAILED_NOTE = "the request failed"
_WORD_FILE_NOTE = "The daily step reads PDF files only; this file is Word"


@dataclass(frozen=True)
class MinutesToReview:
    sitting_date: date
    status_note: str


@dataclass(frozen=True)
class MinutesNotFetched:
    sitting_date: date
    reason: str


@dataclass(frozen=True)
class MinutesStepResult:
    rows_added: int
    rows_listed: int
    files_stored: int
    minutes_to_review: list[MinutesToReview]
    minutes_not_fetched: list[MinutesNotFetched]


@dataclass(frozen=True)
class StoredMinutesFile:
    status: MinutesStatus
    status_note: Optional[str]


@dataclass(frozen=True)
class _FileFields:
    file_format: Optional[MinutesFileFormat]
    extracted_text: Optional[str]
    status: MinutesStatus
    status_note: Optional[str]


@dataclass(frozen=True)
class ListingMove:
    minutes_id: int
    index_row: MinutesIndexRow


@dataclass(frozen=True)
class MinutesPlan:
    index_page: str
    listed_sitting_dates: list[date]
    new_index_rows: list[MinutesIndexRow]
    listing_moves: list[ListingMove]
    not_yet_listed_dates: list[date]
    file_sitting_dates: list[date]


def _read_index_page(index_response: MinutesResponse) -> str:
    if index_response.status_code != _HTTP_OK:
        raise HansardMinutesIndexUnavailableError(
            f"The minutes index page answered {index_response.status_code}"
            f" (x-amzn-waf-action: {index_response.waf_action}, x-cache: {index_response.cache_status})"
        )
    try:
        return index_response.content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HansardMinutesIndexError(
            "The minutes index page is not UTF-8 text"
        ) from error


def _store_live_capture(session: Session, index_page: str) -> Optional[int]:
    capture_url = get_live_capture_url(settings.minutes_index_url, index_page)
    stored_captures = CRUDMinutesIndexCapture(session).get_by_capture_urls(
        [capture_url]
    )
    if stored_captures:
        return stored_captures[0].id
    index_capture = MinutesIndexCapture(
        original_url=settings.minutes_index_url,
        archive_timestamp=None,
        capture_url=capture_url,
        content=index_page,
    )
    CRUDMinutesIndexCapture(session).add_many([index_capture])
    return index_capture.id


def _build_listed_minutes(
    index_row: MinutesIndexRow, index_capture_id: Optional[int]
) -> Minutes:
    return Minutes(
        sitting_date=index_row.sitting_date,
        status=MinutesStatus.LISTED,
        index_source=MinutesIndexSource.LIVE_PAGE,
        index_capture_id=index_capture_id,
        printed_label=index_row.printed_label,
        printed_parliament=index_row.printed_parliament,
        file_url=index_row.file_url,
        file_format=index_row.file_format,
    )


def _get_file_fields(content: bytes, sitting_date: date) -> _FileFields:
    try:
        file_format = get_minutes_file_format(content)
    except HansardMinutesFileError as error:
        return _FileFields(None, None, MinutesStatus.NEEDS_REVIEW, str(error))
    if file_format != MinutesFileFormat.PDF:
        return _FileFields(
            file_format, None, MinutesStatus.NEEDS_REVIEW, _WORD_FILE_NOTE
        )
    try:
        extracted_text = get_minutes_pdf_text(content)
    except HansardMinutesFileError as error:
        return _FileFields(file_format, None, MinutesStatus.NEEDS_REVIEW, str(error))
    text_outcome = get_minutes_text_outcome(sitting_date, extracted_text)
    return _FileFields(
        file_format, extracted_text, text_outcome.status, text_outcome.status_note
    )


def _store_minutes_file(session: Session, minutes: Minutes) -> StoredMinutesFile:
    sitting_date = minutes.sitting_date
    minutes_id = minutes.id
    file_url = minutes.file_url
    if minutes_id is None:
        raise HansardMinutesFileError(f"The minutes of {sitting_date} have no id")
    if file_url is None:
        raise HansardMinutesFileError(
            f"The listed minutes of {sitting_date} have no file address"
        )
    try:
        file_response = get_minutes_file_response(file_url)
    except HansardGatewayError as error:
        logger.warning(f"Minutes file for {sitting_date} not fetched: {error}")
        return StoredMinutesFile(MinutesStatus.LISTED, _REQUEST_FAILED_NOTE)
    if file_response.status_code != _HTTP_OK:
        logger.warning(
            f"Minutes file for {sitting_date} answered {file_response.status_code}"
        )
        return StoredMinutesFile(
            MinutesStatus.LISTED, f"the file answered {file_response.status_code}"
        )
    content = file_response.content
    file_fields = _get_file_fields(content, sitting_date)
    CRUDMinutes(session).set_file_by_id_and_status(
        minutes_id,
        MinutesStatus.LISTED,
        file_fields.status,
        file_fields.status_note,
        file_fields.file_format,
        None,
        hashlib.sha256(content).hexdigest(),
        len(content),
        content,
        datetime.now(timezone.utc),
        file_fields.extracted_text,
    )
    if file_fields.status == MinutesStatus.TEXT_STORED:
        review_note = populate_minutes_divisions(session, minutes_id)
        if review_note is not None:
            session.commit()
            return StoredMinutesFile(MinutesStatus.NEEDS_REVIEW, review_note)
        populate_division_party_counts(
            session,
            [
                division.id
                for division in CRUDDivision(session).get_by_sitting_dates(
                    [sitting_date]
                )
                if division.id is not None
            ],
        )
    session.commit()
    return StoredMinutesFile(file_fields.status, file_fields.status_note)


def get_minutes_plan(session: Session, held_sitting_dates: set[date]) -> MinutesPlan:
    index_page = _read_index_page(get_minutes_index_response())
    report_dates = {
        sitting_date.date()
        for sitting_date in CRUDReport(
            session
        ).get_distinct_sitting_dates_by_sitting_date_from(
            datetime.combine(MINUTES_INDEX_FIRST_DATE, time.min)
        )
    }
    sitting_date_to_index_row = {
        index_row.sitting_date: index_row
        for index_row in parse_live_index_page(index_page, settings.minutes_media_url)
    }
    planned_sitting_dates = sorted(report_dates | set(sitting_date_to_index_row))
    sitting_date_to_stored_minutes = {
        stored_minutes.sitting_date: stored_minutes
        for stored_minutes in CRUDMinutes(session).get_by_sitting_dates(
            planned_sitting_dates
        )
    }
    new_index_rows: list[MinutesIndexRow] = []
    listing_moves: list[ListingMove] = []
    not_yet_listed_dates: list[date] = []
    for sitting_date in planned_sitting_dates:
        stored_minutes = sitting_date_to_stored_minutes.get(sitting_date)
        index_row = sitting_date_to_index_row.get(sitting_date)
        if index_row is None:
            if stored_minutes is None:
                not_yet_listed_dates.append(sitting_date)
            continue
        if stored_minutes is None:
            new_index_rows.append(index_row)
            continue
        if (
            stored_minutes.status == MinutesStatus.NOT_YET_LISTED
            and stored_minutes.id is not None
        ):
            listing_moves.append(ListingMove(stored_minutes.id, index_row))
    sitting_dates_listed_after_store = (
        {
            sitting_date
            for sitting_date, stored_minutes in sitting_date_to_stored_minutes.items()
            if stored_minutes.status == MinutesStatus.LISTED
        }
        | {index_row.sitting_date for index_row in new_index_rows}
        | {listing_move.index_row.sitting_date for listing_move in listing_moves}
    )
    return MinutesPlan(
        index_page,
        sorted(sitting_date_to_index_row),
        new_index_rows,
        listing_moves,
        not_yet_listed_dates,
        sorted((sitting_dates_listed_after_store & report_dates) - held_sitting_dates),
    )


def _store_listing(session: Session, minutes_plan: MinutesPlan) -> None:
    index_capture_id = (
        _store_live_capture(session, minutes_plan.index_page)
        if minutes_plan.new_index_rows or minutes_plan.listing_moves
        else None
    )
    CRUDMinutes(session).add_many(
        [
            _build_listed_minutes(index_row, index_capture_id)
            for index_row in minutes_plan.new_index_rows
        ]
        + [
            Minutes(sitting_date=sitting_date, status=MinutesStatus.NOT_YET_LISTED)
            for sitting_date in minutes_plan.not_yet_listed_dates
        ]
    )
    for listing_move in minutes_plan.listing_moves:
        CRUDMinutes(session).set_listed_by_id_and_status(
            listing_move.minutes_id,
            MinutesStatus.NOT_YET_LISTED,
            MinutesIndexSource.LIVE_PAGE,
            index_capture_id,
            listing_move.index_row.printed_label,
            listing_move.index_row.printed_parliament,
            listing_move.index_row.file_url,
            listing_move.index_row.file_format,
        )
    session.commit()


def populate_minutes(
    session: Session, held_sitting_dates: set[date]
) -> MinutesStepResult:
    minutes_plan = get_minutes_plan(session, held_sitting_dates)
    _store_listing(session, minutes_plan)
    rows_added = len(minutes_plan.new_index_rows) + len(
        minutes_plan.not_yet_listed_dates
    )
    rows_listed = len(minutes_plan.new_index_rows) + len(minutes_plan.listing_moves)
    files_stored = 0
    minutes_to_review: list[MinutesToReview] = []
    minutes_not_fetched: list[MinutesNotFetched] = []
    for listed_minutes in CRUDMinutes(session).get_by_sitting_dates(
        minutes_plan.file_sitting_dates
    ):
        sitting_date = listed_minutes.sitting_date
        stored_minutes_file = _store_minutes_file(session, listed_minutes)
        if stored_minutes_file.status == MinutesStatus.LISTED:
            minutes_not_fetched.append(
                MinutesNotFetched(sitting_date, stored_minutes_file.status_note or "")
            )
        if stored_minutes_file.status == MinutesStatus.TEXT_STORED:
            files_stored += 1
        if stored_minutes_file.status == MinutesStatus.NEEDS_REVIEW:
            minutes_to_review.append(
                MinutesToReview(sitting_date, stored_minutes_file.status_note or "")
            )
    logger.info(
        f"Minutes: {rows_added} rows added, {rows_listed} listed, {files_stored} files stored, {len(minutes_to_review)} to review"
    )
    return MinutesStepResult(
        rows_added,
        rows_listed,
        files_stored,
        minutes_to_review,
        minutes_not_fetched,
    )
