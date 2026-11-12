import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional, TypeVar
from urllib.parse import urlparse, urlunparse

from sqlmodel import Session

from crud.minutes import CRUDMinutes
from database.minutes import Minutes
from enums import MinutesFileFormat, MinutesIndexSource, MinutesStatus
from exceptions import HansardMinutesFileError, HansardWriteCheckError
from schemas.minutes_fetches import MinutesFetches, MinutesFetchRecord
from schemas.minutes_files_plan import (
    FlaggedMinutesFile,
    MinutesFilesPlan,
    PlannedMinutesFile,
)
from services.minutes_text import (
    get_minutes_file_format,
    get_minutes_head_dates,
    get_minutes_pdf_text,
    get_minutes_text_outcome,
    get_minutes_word_text,
    is_minutes_head,
)

FETCH_RECORDS_FILE = "fetches.json"
_NO_FILE_NOTE = "No Archive capture or live address returned a PDF or Word file"
_OLDER_THAN_LIVE_PAGE_NOTE = "No index row or file listing names this sitting; it is older than the live page's oldest row"
_NO_ROUTE_REASON = "no route returned a file"
_NOT_VOTES_AND_PROCEEDINGS_REASON = "the head does not read VOTES AND PROCEEDINGS"
_NO_HEAD_DATE_REASON = "the head prints no date"
_SEVERAL_HEAD_DATES_REASON = "the head prints more than one date"
_INDEX_ROW_EXISTS_REASON = "an index row already gives this date"
_TWO_LISTING_FILES_REASON = "two listing files give this date"
_TWO_STORED_ROWS_REASON = "two stored rows name this address"

_PlannedValueT = TypeVar("_PlannedValueT")


@dataclass(frozen=True)
class _ExtractedFile:
    file_format: Optional[MinutesFileFormat]
    extracted_text: Optional[str]
    file_error: Optional[str]


@dataclass(frozen=True)
class _WinningFile:
    record: MinutesFetchRecord
    extracted_file: _ExtractedFile


@dataclass(frozen=True)
class _ListingFilePlan:
    planned_file: Optional[PlannedMinutesFile]
    flagged_reason: Optional[str]


@dataclass(frozen=True)
class _ListingCandidate:
    file_url: str
    planned_file: PlannedMinutesFile


def _get_address_without_query(file_url: str) -> str:
    return urlunparse(urlparse(file_url)._replace(query=""))


def _get_character_count(extracted_text: Optional[str]) -> Optional[int]:
    return None if extracted_text is None else len(extracted_text)


def _get_text_sha256(extracted_text: Optional[str]) -> Optional[str]:
    if extracted_text is None:
        return None
    return hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()


def _get_extracted_file(content: bytes) -> _ExtractedFile:
    try:
        file_format = get_minutes_file_format(content)
    except HansardMinutesFileError as error:
        return _ExtractedFile(None, None, str(error))
    try:
        if file_format == MinutesFileFormat.PDF:
            return _ExtractedFile(file_format, get_minutes_pdf_text(content), None)
        return _ExtractedFile(file_format, get_minutes_word_text(content), None)
    except HansardMinutesFileError as error:
        return _ExtractedFile(file_format, None, str(error))


def _read_file_content(files_directory: Path, file_name: str) -> bytes:
    try:
        return (files_directory / file_name).read_bytes()
    except FileNotFoundError as error:
        raise HansardMinutesFileError(
            f"The ledger names {file_name}, which is not in the files directory"
        ) from error


def _get_winning_file(
    files_directory: Path, file_url: str, records: list[MinutesFetchRecord]
) -> Optional[_WinningFile]:
    passing_records = [record for record in records if record.is_signature_passed]
    if not passing_records:
        return None
    if len(passing_records) > 1:
        raise HansardMinutesFileError(
            f"{file_url} has {len(passing_records)} records that passed the signature test"
        )
    winner = passing_records[0]
    if winner.file_name is None:
        raise HansardMinutesFileError(
            f"{file_url} has a passing record with no file name"
        )
    content = _read_file_content(files_directory, winner.file_name)
    if hashlib.sha256(content).hexdigest() != winner.sha256:
        raise HansardMinutesFileError(
            f"{winner.file_name} does not hold the SHA-256 the ledger records"
        )
    if len(content) != winner.size_bytes:
        raise HansardMinutesFileError(
            f"{winner.file_name} does not hold the size the ledger records"
        )
    return _WinningFile(winner, _get_extracted_file(content))


def _build_planned_file(
    sitting_date: date,
    file_url: Optional[str],
    is_new_row: bool,
    expected_status: Optional[MinutesStatus],
    status: MinutesStatus,
    status_note: Optional[str],
    index_source: Optional[MinutesIndexSource],
    winning_file: Optional[_WinningFile],
) -> PlannedMinutesFile:
    if winning_file is None:
        return PlannedMinutesFile(
            sitting_date=sitting_date,
            file_url=file_url,
            is_new_row=is_new_row,
            expected_status=expected_status,
            status=status,
            status_note=status_note,
            index_source=index_source,
            file_name=None,
            file_format=None,
            archive_timestamp=None,
            sha256=None,
            size_bytes=None,
            fetched_at=None,
            extracted_character_count=None,
            extracted_text_sha256=None,
        )
    extracted_text = winning_file.extracted_file.extracted_text
    return PlannedMinutesFile(
        sitting_date=sitting_date,
        file_url=file_url,
        is_new_row=is_new_row,
        expected_status=expected_status,
        status=status,
        status_note=status_note,
        index_source=index_source,
        file_name=winning_file.record.file_name,
        file_format=winning_file.extracted_file.file_format,
        archive_timestamp=winning_file.record.archive_timestamp,
        sha256=winning_file.record.sha256,
        size_bytes=winning_file.record.size_bytes,
        fetched_at=winning_file.record.fetched_at,
        extracted_character_count=_get_character_count(extracted_text),
        extracted_text_sha256=_get_text_sha256(extracted_text),
    )


def _get_index_file_plan(
    stored_minutes: Minutes, winning_file: Optional[_WinningFile]
) -> PlannedMinutesFile:
    if winning_file is None:
        return _build_planned_file(
            stored_minutes.sitting_date,
            stored_minutes.file_url,
            False,
            MinutesStatus.LISTED,
            MinutesStatus.FILE_NOT_FOUND,
            _NO_FILE_NOTE,
            None,
            None,
        )
    extracted_text = winning_file.extracted_file.extracted_text
    if extracted_text is None:
        return _build_planned_file(
            stored_minutes.sitting_date,
            stored_minutes.file_url,
            False,
            MinutesStatus.LISTED,
            MinutesStatus.NEEDS_REVIEW,
            winning_file.extracted_file.file_error,
            None,
            winning_file,
        )
    text_outcome = get_minutes_text_outcome(stored_minutes.sitting_date, extracted_text)
    return _build_planned_file(
        stored_minutes.sitting_date,
        stored_minutes.file_url,
        False,
        MinutesStatus.LISTED,
        text_outcome.status,
        text_outcome.status_note,
        None,
        winning_file,
    )


def _get_listing_file_plan(
    file_url: str,
    winning_file: Optional[_WinningFile],
    sitting_date_to_stored_minutes: dict[date, Minutes],
) -> _ListingFilePlan:
    if winning_file is None:
        return _ListingFilePlan(None, _NO_ROUTE_REASON)
    extracted_text = winning_file.extracted_file.extracted_text
    if extracted_text is None:
        return _ListingFilePlan(None, winning_file.extracted_file.file_error)
    if not is_minutes_head(extracted_text):
        return _ListingFilePlan(None, _NOT_VOTES_AND_PROCEEDINGS_REASON)
    head_dates = get_minutes_head_dates(extracted_text)
    if not head_dates:
        return _ListingFilePlan(None, _NO_HEAD_DATE_REASON)
    if len(head_dates) > 1:
        return _ListingFilePlan(None, _SEVERAL_HEAD_DATES_REASON)
    stored_minutes = sitting_date_to_stored_minutes.get(head_dates[0])
    if (
        stored_minutes is not None
        and stored_minutes.status != MinutesStatus.NOT_YET_LISTED
        and stored_minutes.status != MinutesStatus.FILE_NOT_FOUND
    ):
        return _ListingFilePlan(None, _INDEX_ROW_EXISTS_REASON)
    return _ListingFilePlan(
        _build_planned_file(
            head_dates[0],
            file_url,
            stored_minutes is None,
            None if stored_minutes is None else stored_minutes.status,
            MinutesStatus.TEXT_STORED,
            None,
            MinutesIndexSource.ARCHIVE_FILE_LISTING,
            winning_file,
        ),
        None,
    )


def _read_fetch_records(files_directory: Path) -> dict[str, list[MinutesFetchRecord]]:
    fetch_records = MinutesFetches.model_validate_json(
        (files_directory / FETCH_RECORDS_FILE).read_text(encoding="utf8")
    ).root
    file_url_to_records: dict[str, list[MinutesFetchRecord]] = {}
    for fetch_record in fetch_records:
        file_url_to_records.setdefault(fetch_record.file_url, []).append(fetch_record)
    return file_url_to_records


def get_minutes_files_plan(session: Session, files_directory: Path) -> MinutesFilesPlan:
    file_url_to_records = _read_fetch_records(files_directory)
    stored_minutes_rows = CRUDMinutes(session).get_by_statuses(list(MinutesStatus))
    address_to_stored_minutes: dict[str, list[Minutes]] = {}
    for stored_minutes in stored_minutes_rows:
        if stored_minutes.file_url is not None:
            address_to_stored_minutes.setdefault(
                _get_address_without_query(stored_minutes.file_url), []
            ).append(stored_minutes)
    sitting_date_to_stored_minutes = {
        stored_minutes.sitting_date: stored_minutes
        for stored_minutes in stored_minutes_rows
    }
    planned_files: list[PlannedMinutesFile] = []
    flagged_files: list[FlaggedMinutesFile] = []
    sitting_date_to_listing_candidates: defaultdict[date, list[_ListingCandidate]] = (
        defaultdict(list)
    )
    already_stored_count = 0
    for file_url, records in file_url_to_records.items():
        winning_file = _get_winning_file(files_directory, file_url, records)
        stored_rows = address_to_stored_minutes.get(
            _get_address_without_query(file_url), []
        )
        if len(stored_rows) > 1:
            flagged_files.append(
                FlaggedMinutesFile(file_url=file_url, reason=_TWO_STORED_ROWS_REASON)
            )
            continue
        if stored_rows:
            if stored_rows[0].status != MinutesStatus.LISTED:
                already_stored_count += 1
                continue
            planned_files.append(_get_index_file_plan(stored_rows[0], winning_file))
            continue
        listing_file_plan = _get_listing_file_plan(
            file_url, winning_file, sitting_date_to_stored_minutes
        )
        if listing_file_plan.planned_file is None:
            flagged_files.append(
                FlaggedMinutesFile(
                    file_url=file_url, reason=listing_file_plan.flagged_reason or ""
                )
            )
            continue
        sitting_date_to_listing_candidates[
            listing_file_plan.planned_file.sitting_date
        ].append(_ListingCandidate(file_url, listing_file_plan.planned_file))
    for listing_candidates in sitting_date_to_listing_candidates.values():
        if len(listing_candidates) > 1:
            flagged_files.extend(
                FlaggedMinutesFile(
                    file_url=listing_candidate.file_url,
                    reason=_TWO_LISTING_FILES_REASON,
                )
                for listing_candidate in listing_candidates
            )
            continue
        planned_files.append(listing_candidates[0].planned_file)
    live_page_first_date = CRUDMinutes(session).get_min_sitting_date_by_index_source(
        MinutesIndexSource.LIVE_PAGE
    )
    if live_page_first_date is not None:
        planned_dates = {planned_file.sitting_date for planned_file in planned_files}
        planned_files.extend(
            _build_planned_file(
                stored_minutes.sitting_date,
                None,
                False,
                MinutesStatus.NOT_YET_LISTED,
                MinutesStatus.FILE_NOT_FOUND,
                _OLDER_THAN_LIVE_PAGE_NOTE,
                None,
                None,
            )
            for stored_minutes in stored_minutes_rows
            if stored_minutes.status == MinutesStatus.NOT_YET_LISTED
            and stored_minutes.sitting_date < live_page_first_date
            and stored_minutes.sitting_date not in planned_dates
        )
    return MinutesFilesPlan(
        files=sorted(planned_files, key=lambda planned_file: planned_file.sitting_date),
        flagged=flagged_files,
        already_stored_count=already_stored_count,
    )


def _get_planned_value(
    value: Optional[_PlannedValueT], name: str, planned_file: PlannedMinutesFile
) -> _PlannedValueT:
    if value is None:
        raise HansardWriteCheckError(
            f"The planned file of {planned_file.sitting_date} has no {name}"
        )
    return value


def _write_file(
    session: Session,
    minutes_id: int,
    planned_file: PlannedMinutesFile,
    files_directory: Path,
) -> None:
    file_name = _get_planned_value(planned_file.file_name, "file name", planned_file)
    extracted_text = _get_extracted_file(
        _read_file_content(files_directory, file_name)
    ).extracted_text
    if (
        _get_character_count(extracted_text) != planned_file.extracted_character_count
        or _get_text_sha256(extracted_text) != planned_file.extracted_text_sha256
    ):
        raise HansardWriteCheckError(f"The text of {file_name} differs from the plan")
    CRUDMinutes(session).set_file_by_id_and_status(
        minutes_id,
        MinutesStatus.LISTED,
        planned_file.status,
        planned_file.status_note,
        planned_file.file_format,
        planned_file.archive_timestamp,
        _get_planned_value(planned_file.sha256, "SHA-256", planned_file),
        _get_planned_value(planned_file.size_bytes, "size", planned_file),
        None,
        _get_planned_value(planned_file.fetched_at, "fetch time", planned_file),
        extracted_text,
    )


def write_minutes_files_plan(
    session: Session, plan: MinutesFilesPlan, files_directory: Path
) -> None:
    sitting_date_to_minutes_id = {
        stored_minutes.sitting_date: stored_minutes.id
        for stored_minutes in CRUDMinutes(session).get_by_sitting_dates(
            [
                planned_file.sitting_date
                for planned_file in plan.files
                if not planned_file.is_new_row
            ]
        )
        if stored_minutes.id is not None
    }
    for planned_file in plan.files:
        if planned_file.is_new_row:
            new_minutes = Minutes(
                sitting_date=planned_file.sitting_date,
                status=MinutesStatus.LISTED,
                index_source=MinutesIndexSource.ARCHIVE_FILE_LISTING,
                file_url=planned_file.file_url,
                file_format=planned_file.file_format,
            )
            CRUDMinutes(session).add_many([new_minutes])
            minutes_id = _get_planned_value(new_minutes.id, "row id", planned_file)
        else:
            minutes_id = sitting_date_to_minutes_id[planned_file.sitting_date]
        if planned_file.file_name is None:
            CRUDMinutes(session).set_status_by_id_and_status(
                minutes_id,
                _get_planned_value(
                    planned_file.expected_status, "expected status", planned_file
                ),
                planned_file.status,
                planned_file.status_note,
            )
            continue
        if (
            planned_file.index_source == MinutesIndexSource.ARCHIVE_FILE_LISTING
            and not planned_file.is_new_row
        ):
            CRUDMinutes(session).set_listed_by_id_and_status(
                minutes_id,
                _get_planned_value(
                    planned_file.expected_status, "expected status", planned_file
                ),
                MinutesIndexSource.ARCHIVE_FILE_LISTING,
                None,
                None,
                None,
                _get_planned_value(planned_file.file_url, "file address", planned_file),
                _get_planned_value(
                    planned_file.file_format, "file format", planned_file
                ),
            )
        _write_file(session, minutes_id, planned_file, files_directory)
