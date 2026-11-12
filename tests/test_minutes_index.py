import json
import re
from datetime import date
from pathlib import Path

import pytest

from enums import MinutesFileFormat
from exceptions import HansardMinutesIndexError
from services.minutes_index import (
    MinutesIndexRow,
    get_live_capture_url,
    parse_archive_index_page,
    parse_live_index_page,
)

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures" / "minutes_index"
_MEDIA_URL = "https://media.example/api/media"
_INDEX_URL = (
    "https://www.parliament.gov.sg/parliamentary-business/votes-and-proceedings"
)
_PUSH_PATTERN = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_SHA256_SUFFIX_PATTERN = re.compile(r"#sha256=[0-9a-f]{64}$")
_EMPTY_LIVE_ROWS_TEXT = '{"initialMPs":{"meta":{"filter_count":0},"data":[]}}'
_LIVE_ROW_COUNT = 3
_FIRST_LIVE_REPORT_ID = "d49b346d-4a2a-4a2d-a13a-c53e6642d7fc"
_ARCHIVE_2021_URL = "https://www.parliament.gov.sg/docs/default-source/default-document-library/vp-3aug21.pdf?sfvrsn=aa9ad958_0"
_ARCHIVE_NAMED_CAPTURE_URL = "https://www.parliament.gov.sg/docs/default-source/Votes-and-Proceedings/vnp20110052.doc?sfvrsn=1f667b08_0"


def _read_fixture(name: str) -> str:
    return (_FIXTURE_DIRECTORY / name).read_text(encoding="utf-8")


def _build_live_page(rows_text: str) -> str:
    return f"<html><body><script>self.__next_f.push([1,{json.dumps(rows_text)}])</script></body></html>"


def _read_live_rows_text() -> str:
    match = _PUSH_PATTERN.search(_read_fixture("live-index-3-rows.html"))
    assert match is not None
    return json.loads(match.group(1))


def test_live_page_rows_carry_date_label_parliament_and_built_address() -> None:
    rows = parse_live_index_page(_read_fixture("live-index-3-rows.html"), _MEDIA_URL)

    assert len(rows) == _LIVE_ROW_COUNT
    assert rows[0] == MinutesIndexRow(
        date(2026, 8, 5),
        "Votes and Proceedings No. 34",
        "15th Parliament",
        f"{_MEDIA_URL}/{_FIRST_LIVE_REPORT_ID}/VP-5Aug2026.pdf",
        MinutesFileFormat.PDF,
        "Votes and Proceedings No. 34; date 2026-08-05T12:00:00; 15th Parliament; file VP-5Aug2026.pdf",
    )


def test_live_page_without_initial_rows_raises() -> None:
    with pytest.raises(HansardMinutesIndexError):
        parse_live_index_page("<html><body></body></html>", _MEDIA_URL)


def test_live_page_with_a_row_without_a_date_raises() -> None:
    rows_text = _read_live_rows_text()
    date_start = rows_text.index('"date":"')
    date_end = rows_text.index('"', date_start + len('"date":"'))
    broken_text = rows_text[: date_start + len('"date":"')] + "soon" + rows_text[date_end:]

    with pytest.raises(HansardMinutesIndexError):
        parse_live_index_page(_build_live_page(broken_text), _MEDIA_URL)


def test_live_page_with_an_unknown_media_type_raises() -> None:
    rows_text = _read_live_rows_text().replace("application/pdf", "text/plain", 1)

    with pytest.raises(HansardMinutesIndexError):
        parse_live_index_page(_build_live_page(rows_text), _MEDIA_URL)


def test_live_page_with_no_rows_is_empty() -> None:
    assert (
        parse_live_index_page(_build_live_page(_EMPTY_LIVE_ROWS_TEXT), _MEDIA_URL)
        == []
    )


def test_archive_page_rows_carry_date_label_parliament_and_absolute_address() -> None:
    rows = parse_archive_index_page(_read_fixture("archive-index-2021-08.html"), _INDEX_URL)

    assert rows[0] == MinutesIndexRow(
        date(2021, 8, 3),
        "Votes and Proceedings No. 36",
        "14th Parliament",
        _ARCHIVE_2021_URL,
        MinutesFileFormat.PDF,
        "Votes and Proceedings No. 36 Sitting on 3 August 2021 14th Parliament",
    )


def test_archive_word_row_is_word() -> None:
    rows = parse_archive_index_page(
        _read_fixture("archive-index-2010-03-doc.html"), _INDEX_URL
    )
    third_march_row = next(row for row in rows if row.sitting_date == date(2010, 3, 3))

    assert third_march_row.file_format == MinutesFileFormat.WORD
    assert third_march_row.printed_label == "Votes and Proceedings No. 18"
    assert third_march_row.printed_parliament == "11th Parliament"


def test_archive_named_capture_label_comes_from_the_span() -> None:
    rows = parse_archive_index_page(
        _read_fixture("archive-index-2025-06-named-capture.html"), _INDEX_URL
    )

    assert rows[0] == MinutesIndexRow(
        date(2011, 4, 11),
        "Votes and Proceedings No. 52 (DOC, 79.87 KB)",
        "11th Parliament",
        _ARCHIVE_NAMED_CAPTURE_URL,
        MinutesFileFormat.WORD,
        "Votes and Proceedings No. 52 (DOC, 79.87 KB) Sitting on 11 April 2011 11th Parliament",
    )


def test_archive_row_with_neither_heading_nor_span_raises() -> None:
    page = _read_fixture("archive-index-2025-06-named-capture.html")
    page = re.sub(r"<span>.*?</span>", "", page)

    with pytest.raises(HansardMinutesIndexError):
        parse_archive_index_page(page, _INDEX_URL)


def test_archive_row_with_a_heading_and_no_span_keeps_the_heading_text() -> None:
    rows = parse_archive_index_page(_read_fixture("archive-index-2021-08.html"), _INDEX_URL)

    assert rows[0].printed_label == "Votes and Proceedings No. 36"


def test_archive_row_without_a_parseable_date_raises() -> None:
    page = _read_fixture("archive-index-2021-08.html").replace(
        "Sitting on 3 August 2021", "Sitting on Soonday"
    )

    with pytest.raises(HansardMinutesIndexError):
        parse_archive_index_page(page, _INDEX_URL)


def test_archive_row_with_an_unknown_extension_raises() -> None:
    page = _read_fixture("archive-index-2021-08.html").replace(".pdf", ".xls")

    with pytest.raises(HansardMinutesIndexError):
        parse_archive_index_page(page, _INDEX_URL)


def test_archive_page_without_rows_is_empty() -> None:
    assert parse_archive_index_page("<html><body></body></html>", _INDEX_URL) == []


def test_live_capture_url_changes_with_the_content() -> None:
    first_address = get_live_capture_url(_INDEX_URL, "first content")
    second_address = get_live_capture_url(_INDEX_URL, "second content")

    assert first_address != second_address
    assert first_address == get_live_capture_url(_INDEX_URL, "first content")
    assert _SHA256_SUFFIX_PATTERN.search(first_address) is not None
    assert _SHA256_SUFFIX_PATTERN.search(second_address) is not None
    assert first_address.startswith(f"{_INDEX_URL}#sha256=")
