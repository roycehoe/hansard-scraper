from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Optional

from sqlmodel import Session

from crud.minutes import CRUDMinutes
from crud.minutes_index_capture import CRUDMinutesIndexCapture
from crud.report import CRUDReport
from database.minutes import Minutes, MinutesIndexCapture
from enums import MinutesIndexSource, MinutesStatus
from exceptions import HansardWriteCheckError
from schemas.minutes_index_capture import (
    MinutesIndexCaptureManifest,
    MinutesIndexCaptureManifestEntry,
)
from schemas.minutes_index_plan import (
    MinutesIndexPlan,
    PlannedMinutesIndexCapture,
    PlannedMinutesRow,
)
from services.minutes_index import (
    MINUTES_INDEX_FIRST_DATE,
    MinutesIndexRow,
    parse_archive_index_page,
    parse_live_index_page,
)
from settings import settings

_MANIFEST_FILE_NAME = "captures.json"


@dataclass(frozen=True)
class _SourcedIndexRow:
    index_row: MinutesIndexRow
    index_source: MinutesIndexSource
    capture_url: str


@dataclass(frozen=True)
class _CaptureReading:
    planned_captures: list[PlannedMinutesIndexCapture]
    sitting_date_to_kept_row: dict[date, _SourcedIndexRow]
    duplicate_count: int
    conflicting_address_count: int


def _get_capture_rows(
    manifest_entry: MinutesIndexCaptureManifestEntry, captures_directory: Path
) -> list[MinutesIndexRow]:
    page = (captures_directory / manifest_entry.file).read_text()
    if manifest_entry.archive_timestamp is None:
        return parse_live_index_page(page, settings.minutes_media_url)
    return parse_archive_index_page(page, settings.minutes_index_url)


def _get_planned_row(
    sitting_date: date,
    stored_minutes: Optional[Minutes],
    sourced_row: Optional[_SourcedIndexRow],
) -> Optional[PlannedMinutesRow]:
    if sourced_row is None:
        if stored_minutes is not None:
            return None
        return PlannedMinutesRow(
            sitting_date=sitting_date,
            status=MinutesStatus.NOT_YET_LISTED,
            is_new_row=True,
            expected_status=None,
            index_source=None,
            capture_url=None,
            printed_label=None,
            printed_parliament=None,
            file_url=None,
            file_format=None,
        )
    index_row = sourced_row.index_row
    if stored_minutes is not None:
        is_not_yet_listed = stored_minutes.status == MinutesStatus.NOT_YET_LISTED
        is_file_at_new_address = (
            stored_minutes.status == MinutesStatus.FILE_NOT_FOUND
            and stored_minutes.file_url != index_row.file_url
        )
        if not is_not_yet_listed and not is_file_at_new_address:
            return None
    return PlannedMinutesRow(
        sitting_date=sitting_date,
        status=MinutesStatus.LISTED,
        is_new_row=stored_minutes is None,
        expected_status=None if stored_minutes is None else stored_minutes.status,
        index_source=sourced_row.index_source,
        capture_url=sourced_row.capture_url,
        printed_label=index_row.printed_label,
        printed_parliament=index_row.printed_parliament,
        file_url=index_row.file_url,
        file_format=index_row.file_format,
    )


def _read_captures(captures_directory: Path) -> _CaptureReading:
    manifest = MinutesIndexCaptureManifest.model_validate_json(
        (captures_directory / _MANIFEST_FILE_NAME).read_bytes()
    )
    live_entries = [
        manifest_entry
        for manifest_entry in manifest.root
        if manifest_entry.archive_timestamp is None
    ]
    archive_entries = sorted(
        (
            manifest_entry
            for manifest_entry in manifest.root
            if manifest_entry.archive_timestamp is not None
        ),
        key=lambda manifest_entry: manifest_entry.archive_timestamp or "",
        reverse=True,
    )
    planned_captures: list[PlannedMinutesIndexCapture] = []
    sitting_date_to_kept_row: dict[date, _SourcedIndexRow] = {}
    conflicting_sitting_dates: set[date] = set()
    row_count = 0
    for manifest_entry in live_entries + archive_entries:
        capture_rows = _get_capture_rows(manifest_entry, captures_directory)
        planned_captures.append(
            PlannedMinutesIndexCapture(
                file=manifest_entry.file,
                original_url=manifest_entry.original_url,
                archive_timestamp=manifest_entry.archive_timestamp,
                capture_url=manifest_entry.capture_url,
                row_count=len(capture_rows),
            )
        )
        index_source = (
            MinutesIndexSource.LIVE_PAGE
            if manifest_entry.archive_timestamp is None
            else MinutesIndexSource.ARCHIVE_INDEX_CAPTURE
        )
        row_count += len(capture_rows)
        for capture_row in capture_rows:
            kept_row = sitting_date_to_kept_row.get(capture_row.sitting_date)
            if kept_row is None:
                sitting_date_to_kept_row[capture_row.sitting_date] = _SourcedIndexRow(
                    capture_row, index_source, manifest_entry.capture_url
                )
                continue
            if kept_row.index_row.file_url != capture_row.file_url:
                conflicting_sitting_dates.add(capture_row.sitting_date)
    return _CaptureReading(
        planned_captures=planned_captures,
        sitting_date_to_kept_row=sitting_date_to_kept_row,
        duplicate_count=row_count - len(sitting_date_to_kept_row),
        conflicting_address_count=len(conflicting_sitting_dates),
    )


def get_minutes_index_plan(
    session: Session, captures_directory: Path
) -> MinutesIndexPlan:
    capture_reading = _read_captures(captures_directory)
    report_dates = {
        sitting_date.date()
        for sitting_date in CRUDReport(
            session
        ).get_distinct_sitting_dates_by_sitting_date_from(
            datetime.combine(MINUTES_INDEX_FIRST_DATE, time.min)
        )
    }
    planned_sitting_dates = sorted(
        set(capture_reading.sitting_date_to_kept_row) | report_dates
    )
    sitting_date_to_stored_minutes = {
        stored_minutes.sitting_date: stored_minutes
        for stored_minutes in CRUDMinutes(session).get_by_sitting_dates(
            planned_sitting_dates
        )
    }
    planned_rows: list[PlannedMinutesRow] = []
    for sitting_date in planned_sitting_dates:
        planned_row = _get_planned_row(
            sitting_date,
            sitting_date_to_stored_minutes.get(sitting_date),
            capture_reading.sitting_date_to_kept_row.get(sitting_date),
        )
        if planned_row is not None:
            planned_rows.append(planned_row)
    return MinutesIndexPlan(
        captures=capture_reading.planned_captures,
        rows=planned_rows,
        duplicate_count=capture_reading.duplicate_count,
        conflicting_address_count=capture_reading.conflicting_address_count,
        stored_row_count=len(planned_sitting_dates) - len(planned_rows),
    )


def _get_index_capture_id(
    capture_url_to_id: dict[str, int], capture_url: Optional[str]
) -> Optional[int]:
    if capture_url is None:
        return None
    return capture_url_to_id[capture_url]


def _set_row_listed(
    session: Session,
    minutes_id: int,
    planned_row: PlannedMinutesRow,
    index_capture_id: Optional[int],
) -> None:
    if planned_row.expected_status is None:
        raise HansardWriteCheckError(
            f"The planned move of {planned_row.sitting_date} has no expected status"
        )
    if planned_row.index_source is None:
        raise HansardWriteCheckError(
            f"The planned move of {planned_row.sitting_date} has no index source"
        )
    if planned_row.file_url is None:
        raise HansardWriteCheckError(
            f"The planned move of {planned_row.sitting_date} has no file address"
        )
    if planned_row.file_format is None:
        raise HansardWriteCheckError(
            f"The planned move of {planned_row.sitting_date} has no file format"
        )
    CRUDMinutes(session).set_listed_by_id_and_status(
        minutes_id,
        planned_row.expected_status,
        planned_row.index_source,
        index_capture_id,
        planned_row.printed_label,
        planned_row.printed_parliament,
        planned_row.file_url,
        planned_row.file_format,
    )


def write_minutes_index_plan(
    session: Session, plan: MinutesIndexPlan, captures_directory: Path
) -> None:
    planned_capture_urls = [
        planned_capture.capture_url for planned_capture in plan.captures
    ]
    stored_capture_urls = {
        capture_row.capture_url
        for capture_row in CRUDMinutesIndexCapture(session).get_by_capture_urls(
            planned_capture_urls
        )
    }
    CRUDMinutesIndexCapture(session).add_many(
        [
            MinutesIndexCapture(
                original_url=planned_capture.original_url,
                archive_timestamp=planned_capture.archive_timestamp,
                capture_url=planned_capture.capture_url,
                content=(captures_directory / planned_capture.file).read_text(),
            )
            for planned_capture in plan.captures
            if planned_capture.capture_url not in stored_capture_urls
        ]
    )
    capture_url_to_id = {
        capture_row.capture_url: capture_row.id
        for capture_row in CRUDMinutesIndexCapture(session).get_by_capture_urls(
            planned_capture_urls
        )
    }
    new_minutes_rows: list[Minutes] = []
    moved_rows: list[PlannedMinutesRow] = []
    for planned_row in plan.rows:
        if not planned_row.is_new_row:
            moved_rows.append(planned_row)
            continue
        new_minutes_rows.append(
            Minutes(
                sitting_date=planned_row.sitting_date,
                status=planned_row.status,
                index_source=planned_row.index_source,
                index_capture_id=_get_index_capture_id(
                    capture_url_to_id, planned_row.capture_url
                ),
                printed_label=planned_row.printed_label,
                printed_parliament=planned_row.printed_parliament,
                file_url=planned_row.file_url,
                file_format=planned_row.file_format,
            )
        )
    CRUDMinutes(session).add_many(new_minutes_rows)
    sitting_date_to_minutes_id = {
        stored_minutes.sitting_date: stored_minutes.id
        for stored_minutes in CRUDMinutes(session).get_by_sitting_dates(
            [moved_row.sitting_date for moved_row in moved_rows]
        )
        if stored_minutes.id is not None
    }
    for moved_row in moved_rows:
        _set_row_listed(
            session,
            sitting_date_to_minutes_id[moved_row.sitting_date],
            moved_row,
            _get_index_capture_id(capture_url_to_id, moved_row.capture_url),
        )
