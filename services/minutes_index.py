import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import PurePosixPath
from typing import Optional
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup
from bs4.element import Tag
from pydantic import ValidationError

from enums import MinutesFileFormat
from exceptions import HansardMinutesIndexError
from schemas.minutes_index_page import LiveMinutesIndex, LiveMinutesRow

MINUTES_INDEX_FIRST_DATE = date(2005, 1, 12)

_FLIGHT_PUSH_PATTERN = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_INITIAL_ROWS_KEY = '"initialMPs":'
_MEDIA_TYPE_TO_FILE_FORMAT = {
    "application/pdf": MinutesFileFormat.PDF,
    "application/msword": MinutesFileFormat.WORD,
}
_EXTENSION_TO_FILE_FORMAT = {
    ".pdf": MinutesFileFormat.PDF,
    ".doc": MinutesFileFormat.WORD,
}
_SITTING_ON_PATTERN = re.compile(r"Sitting on\s+(\d{1,2}\s+[A-Za-z]+\s+\d{4})")
_ARCHIVE_DATE_FORMAT = "%d %B %Y"
_SITTING_DATE_COLUMN_INDEX = 1
_PARLIAMENT_COLUMN_INDEX = 2


@dataclass(frozen=True)
class MinutesIndexRow:
    sitting_date: date
    printed_label: str
    printed_parliament: Optional[str]
    file_url: str
    file_format: MinutesFileFormat
    printed_text: str


def _read_live_index(page: str) -> LiveMinutesIndex:
    try:
        for match in _FLIGHT_PUSH_PATTERN.finditer(page):
            text = json.loads(match.group(1))
            if _INITIAL_ROWS_KEY not in text:
                continue
            rows_object, _ = json.JSONDecoder().raw_decode(
                text[text.index(_INITIAL_ROWS_KEY) + len(_INITIAL_ROWS_KEY) :]
            )
            return LiveMinutesIndex.model_validate(rows_object)
    except ValidationError as error:
        raise HansardMinutesIndexError(
            "The live index page rows do not match the expected shape"
        ) from error
    except json.JSONDecodeError as error:
        raise HansardMinutesIndexError(
            "The live index page rows are not readable JSON"
        ) from error
    raise HansardMinutesIndexError("The live index page holds no initialMPs rows")


def _build_live_row(
    live_minutes_row: LiveMinutesRow, media_url: str
) -> MinutesIndexRow:
    try:
        sitting_date = datetime.fromisoformat(live_minutes_row.date).date()
    except ValueError as error:
        raise HansardMinutesIndexError(
            f"The live row {live_minutes_row.description!r} has no parseable date"
        ) from error
    try:
        file_format = _MEDIA_TYPE_TO_FILE_FORMAT[live_minutes_row.report.type]
    except KeyError as error:
        raise HansardMinutesIndexError(
            f"The live row {live_minutes_row.description!r} has the unknown media type {live_minutes_row.report.type!r}"
        ) from error
    printed_parliament = (
        None
        if live_minutes_row.parliaments is None
        else live_minutes_row.parliaments.title
    )
    return MinutesIndexRow(
        sitting_date=sitting_date,
        printed_label=live_minutes_row.description,
        printed_parliament=printed_parliament,
        file_url=f"{media_url}/{live_minutes_row.report.id}/{quote(live_minutes_row.report.filename_download, safe='')}",
        file_format=file_format,
        printed_text=f"{live_minutes_row.description}; date {live_minutes_row.date}; {printed_parliament}; file {live_minutes_row.report.filename_download}",
    )


def parse_live_index_page(page: str, media_url: str) -> list[MinutesIndexRow]:
    live_index = _read_live_index(page)
    return [
        _build_live_row(live_minutes_row, media_url)
        for live_minutes_row in live_index.data
    ]


def _read_archive_label(individual_vote_element: Tag, file_url: str) -> str:
    heading_element = individual_vote_element.select_one("h5")
    if heading_element is not None:
        return heading_element.get_text(" ", strip=True)
    span_element = individual_vote_element.select_one("a span")
    if span_element is None:
        raise HansardMinutesIndexError(f"The archive row of {file_url} has no label")
    return span_element.get_text(" ", strip=True)


def _read_archive_sitting_date(columns: list[Tag], printed_label: str) -> date:
    try:
        column_text = columns[_SITTING_DATE_COLUMN_INDEX].get_text(" ", strip=True)
    except IndexError as error:
        raise HansardMinutesIndexError(
            f"The archive row {printed_label!r} has no sitting date column"
        ) from error
    match = _SITTING_ON_PATTERN.search(column_text)
    if match is None:
        raise HansardMinutesIndexError(
            f"The archive row {printed_label!r} has no sitting date"
        )
    try:
        return datetime.strptime(match.group(1), _ARCHIVE_DATE_FORMAT).date()
    except ValueError as error:
        raise HansardMinutesIndexError(
            f"The archive row {printed_label!r} has an impossible sitting date"
        ) from error


def _read_archive_parliament(columns: list[Tag]) -> Optional[str]:
    try:
        return columns[_PARLIAMENT_COLUMN_INDEX].get_text(" ", strip=True) or None
    except IndexError:
        return None


def _read_archive_file_format(file_url: str) -> MinutesFileFormat:
    extension = PurePosixPath(urlparse(file_url).path).suffix.lower()
    try:
        return _EXTENSION_TO_FILE_FORMAT[extension]
    except KeyError as error:
        raise HansardMinutesIndexError(
            f"The archive file {file_url} has the unknown extension {extension!r}"
        ) from error


def _build_archive_row(individual_vote_element: Tag, index_url: str) -> MinutesIndexRow:
    anchor = individual_vote_element.select_one("a[href]")
    if anchor is None:
        raise HansardMinutesIndexError("An archive row holds no file link")
    href = anchor.get("href")
    if not isinstance(href, str):
        raise HansardMinutesIndexError("An archive row's file link has no address")
    file_url = urljoin(index_url, href)
    printed_label = _read_archive_label(individual_vote_element, file_url)
    columns = individual_vote_element.select("div.vp-title > div")
    return MinutesIndexRow(
        sitting_date=_read_archive_sitting_date(columns, printed_label),
        printed_label=printed_label,
        printed_parliament=_read_archive_parliament(columns),
        file_url=file_url,
        file_format=_read_archive_file_format(file_url),
        printed_text=individual_vote_element.get_text(" ", strip=True),
    )


def parse_archive_index_page(page: str, index_url: str) -> list[MinutesIndexRow]:
    soup = BeautifulSoup(page, "html.parser")
    return [
        _build_archive_row(individual_vote_element, index_url)
        for individual_vote_element in soup.select("div.indv-votes")
    ]


def get_live_capture_url(original_url: str, content: str) -> str:
    return (
        f"{original_url}#sha256={hashlib.sha256(content.encode('utf-8')).hexdigest()}"
    )
