import hashlib
import io
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pytest
from pypdf import PdfWriter
from sqlalchemy.engine import Engine
from sqlmodel import Session, func, select

import populate.minutes as minutes_step
from crud.minutes import CRUDMinutes
from database.minutes import Minutes, MinutesIndexCapture
from enums import (
    MinutesFileFormat,
    MinutesIndexSource,
    MinutesStatus,
)
from exceptions import (
    HansardGatewayError,
    HansardMinutesIndexError,
    HansardMinutesIndexUnavailableError,
)
from schemas.minutes_response import MinutesResponse
from settings import settings
from tests.division_seed import add_division_report
from tests.refresh_fixtures import (
    FakeParliament,
    build_live_index_page,
    build_live_index_row,
)

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures" / "minutes"
_PDF_FIXTURE = "vp-10jan18-first-pages.pdf"
_WORD_FIXTURE = "vp0592008_7.doc"
_PDF_DATE = date(2018, 1, 10)
_OTHER_DATE = date(2018, 1, 11)
_FILE_ID = "file-id-a"
_FILE_NAME = "VP-10Jan2018.pdf"
_OTHER_FILE_ID = "file-id-b"
_OTHER_FILE_NAME = "VP-11Jan2018.pdf"
_FILE_URL = f"{settings.minutes_media_url}/{_FILE_ID}/{_FILE_NAME}"
_OTHER_FILE_URL = f"{settings.minutes_media_url}/{_OTHER_FILE_ID}/{_OTHER_FILE_NAME}"
_FILE_NUMBER = 57
_BLANK_PAGE_SIZE = 200
_HTTP_NOT_FOUND = 404
_HTTP_FORBIDDEN = 403
_MOVED_DATE = date(2018, 1, 10)
_NEW_LISTED_DATE = date(2018, 1, 11)
_UNLISTED_DATE = date(2018, 1, 12)
_HELD_DATE = date(2018, 1, 15)
_NO_REPORT_DATE = date(2018, 1, 16)
_STORED_LISTED_DATE = date(2018, 1, 17)


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


def _read_fixture(name: str) -> bytes:
    return (_FIXTURE_DIRECTORY / name).read_bytes()


def _build_blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=_BLANK_PAGE_SIZE, height=_BLANK_PAGE_SIZE)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _add_report(session: Session, sitting_date: date, report_id: str) -> None:
    add_division_report(
        session,
        report_id,
        datetime(sitting_date.year, sitting_date.month, sitting_date.day),
    )
    session.commit()


def _add_minutes(session: Session, minutes: Minutes) -> int:
    CRUDMinutes(session).add_many([minutes])
    session.commit()
    assert minutes.id is not None
    return minutes.id


def _add_listed_minutes(session: Session, sitting_date: date, file_url: str) -> int:
    return _add_minutes(
        session,
        Minutes(
            sitting_date=sitting_date,
            status=MinutesStatus.LISTED,
            index_source=MinutesIndexSource.LIVE_PAGE,
            file_url=file_url,
            file_format=MinutesFileFormat.PDF,
        ),
    )


def _get_minutes(session: Session, sitting_date: date) -> Optional[Minutes]:
    session.expire_all()
    stored_rows = CRUDMinutes(session).get_by_sitting_dates([sitting_date])
    return stored_rows[0] if stored_rows else None


def _get_capture_count(session: Session) -> int:
    return session.exec(select(func.count()).select_from(MinutesIndexCapture)).one()


def _list_dates(fake_parliament: FakeParliament, listed_dates: list[date]) -> None:
    fake_parliament.minutes_index_page = build_live_index_page(
        [
            build_live_index_row(
                listed_date,
                _FILE_NUMBER,
                _FILE_ID if listed_date == _PDF_DATE else _OTHER_FILE_ID,
                _FILE_NAME if listed_date == _PDF_DATE else _OTHER_FILE_NAME,
            )
            for listed_date in listed_dates
        ]
    )


def _answer_file(
    fake_parliament: FakeParliament,
    file_url: str,
    content: bytes,
    status_code: int = 200,
) -> None:
    fake_parliament.file_url_to_response[file_url] = MinutesResponse(
        url=file_url, status_code=status_code, content=content
    )


def test_new_report_date_gets_a_not_yet_listed_row(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _add_report(scratch_session, _PDF_DATE, "R1")

    result = minutes_step.populate_minutes(scratch_session, set())

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.NOT_YET_LISTED
    assert stored_minutes.file_url is None
    assert (result.rows_added, result.rows_listed) == (1, 0)


def test_report_date_before_the_first_index_date_gets_none(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _add_report(scratch_session, date(2004, 1, 4), "R1")

    minutes_step.populate_minutes(scratch_session, set())

    assert _get_minutes(scratch_session, date(2004, 1, 4)) is None


def test_index_row_lists_a_new_date_and_stores_one_live_capture(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _list_dates(fake_parliament, [_PDF_DATE, _OTHER_DATE])

    result = minutes_step.populate_minutes(scratch_session, set())

    assert _get_capture_count(scratch_session) == 1
    capture = scratch_session.exec(select(MinutesIndexCapture)).one()
    assert capture.archive_timestamp is None
    assert capture.original_url == settings.minutes_index_url
    for sitting_date in (_PDF_DATE, _OTHER_DATE):
        stored_minutes = _get_minutes(scratch_session, sitting_date)
        assert stored_minutes is not None
        assert stored_minutes.status == MinutesStatus.LISTED
        assert stored_minutes.index_source == MinutesIndexSource.LIVE_PAGE
        assert stored_minutes.index_capture_id == capture.id
    assert (result.rows_added, result.rows_listed) == (2, 2)


def test_page_that_lists_nothing_new_stores_no_capture(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _list_dates(fake_parliament, [_PDF_DATE])
    minutes_step.populate_minutes(scratch_session, set())

    result = minutes_step.populate_minutes(scratch_session, set())

    assert _get_capture_count(scratch_session) == 1
    assert (result.rows_added, result.rows_listed) == (0, 0)


def test_not_yet_listed_row_moves_to_listed_when_the_index_shows_it(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    first_id = _add_minutes(
        scratch_session,
        Minutes(sitting_date=_PDF_DATE, status=MinutesStatus.NOT_YET_LISTED),
    )
    _list_dates(fake_parliament, [_PDF_DATE])

    result = minutes_step.populate_minutes(scratch_session, set())

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.id == first_id
    assert stored_minutes.status == MinutesStatus.LISTED
    assert stored_minutes.file_url == _FILE_URL
    assert stored_minutes.index_capture_id is not None
    assert (result.rows_added, result.rows_listed) == (0, 1)


def test_listed_file_is_fetched_and_its_text_stored(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _add_report(scratch_session, _PDF_DATE, "R1")
    _list_dates(fake_parliament, [_PDF_DATE])
    content = _read_fixture(_PDF_FIXTURE)
    _answer_file(fake_parliament, _FILE_URL, content)

    result = minutes_step.populate_minutes(scratch_session, set())

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.TEXT_STORED
    assert stored_minutes.sha256 == hashlib.sha256(content).hexdigest()
    assert stored_minutes.size_bytes == len(content)
    assert stored_minutes.file_bytes == content
    assert stored_minutes.fetched_at is not None
    assert stored_minutes.fetched_at.tzinfo is not None
    assert stored_minutes.archive_timestamp is None
    assert stored_minutes.extracted_text is not None
    assert "JANUARY 2018" in stored_minutes.extracted_text
    assert (result.rows_added, result.rows_listed, result.files_stored) == (1, 1, 1)
    assert result.minutes_to_review == []


def test_held_date_and_date_without_a_report_are_not_fetched(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _add_report(scratch_session, _PDF_DATE, "R1")
    _add_listed_minutes(scratch_session, _PDF_DATE, _FILE_URL)
    _add_listed_minutes(scratch_session, _OTHER_DATE, _OTHER_FILE_URL)

    minutes_step.populate_minutes(scratch_session, {_PDF_DATE})

    assert fake_parliament.minutes_file_calls == []
    for sitting_date in (_PDF_DATE, _OTHER_DATE):
        stored_minutes = _get_minutes(scratch_session, sitting_date)
        assert stored_minutes is not None
        assert stored_minutes.status == MinutesStatus.LISTED


def test_network_failure_and_non_200_leave_the_row_listed(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _add_report(scratch_session, _PDF_DATE, "R1")
    _add_listed_minutes(scratch_session, _PDF_DATE, _FILE_URL)

    for status_code, expected_reason in (
        (None, "the request failed"),
        (_HTTP_NOT_FOUND, "the file answered 404"),
        (_HTTP_FORBIDDEN, "the file answered 403"),
    ):
        if status_code is not None:
            _answer_file(fake_parliament, _FILE_URL, b"", status_code)

        result = minutes_step.populate_minutes(scratch_session, set())

        assert [
            (minutes_not_fetched.sitting_date, minutes_not_fetched.reason)
            for minutes_not_fetched in result.minutes_not_fetched
        ] == [(_PDF_DATE, expected_reason)]

        stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
        assert stored_minutes is not None
        assert stored_minutes.status == MinutesStatus.LISTED
        assert stored_minutes.sha256 is None
        assert result.minutes_to_review == []
    assert fake_parliament.minutes_file_calls == [_FILE_URL] * 3


@pytest.mark.parametrize(
    "content",
    [b"not a pdf", _build_blank_pdf(), _read_fixture(_WORD_FIXTURE)],
    ids=["not-a-pdf", "scan", "word"],
)
def test_unreadable_scan_and_non_pdf_become_needs_review(
    content: bytes, scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _add_report(scratch_session, _PDF_DATE, "R1")
    _add_listed_minutes(scratch_session, _PDF_DATE, _FILE_URL)
    _answer_file(fake_parliament, _FILE_URL, content)

    result = minutes_step.populate_minutes(scratch_session, set())

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.NEEDS_REVIEW
    assert stored_minutes.status_note
    assert stored_minutes.sha256 == hashlib.sha256(content).hexdigest()
    assert stored_minutes.size_bytes == len(content)
    assert stored_minutes.file_bytes == content
    assert stored_minutes.extracted_text is None
    assert [
        (minutes_to_review.sitting_date, minutes_to_review.status_note)
        for minutes_to_review in result.minutes_to_review
    ] == [(_PDF_DATE, stored_minutes.status_note)]


def test_scan_keeps_its_pdf_format_when_extraction_fails(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _add_report(scratch_session, _PDF_DATE, "R1")
    _add_listed_minutes(scratch_session, _PDF_DATE, _FILE_URL)
    _answer_file(fake_parliament, _FILE_URL, _build_blank_pdf())

    minutes_step.populate_minutes(scratch_session, set())

    stored_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.NEEDS_REVIEW
    assert stored_minutes.file_format == MinutesFileFormat.PDF


def test_head_date_mismatch_becomes_needs_review(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _add_report(scratch_session, _OTHER_DATE, "R1")
    _add_listed_minutes(scratch_session, _OTHER_DATE, _OTHER_FILE_URL)
    _answer_file(fake_parliament, _OTHER_FILE_URL, _read_fixture(_PDF_FIXTURE))

    result = minutes_step.populate_minutes(scratch_session, set())

    stored_minutes = _get_minutes(scratch_session, _OTHER_DATE)
    assert stored_minutes is not None
    assert stored_minutes.status == MinutesStatus.NEEDS_REVIEW
    assert stored_minutes.status_note is not None
    assert "10 January 2018" in stored_minutes.status_note
    assert [
        minutes_to_review.sitting_date for minutes_to_review in result.minutes_to_review
    ] == [_OTHER_DATE]


def test_each_file_commits_on_its_own(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add_report(scratch_session, _PDF_DATE, "R1")
    _add_report(scratch_session, _OTHER_DATE, "R2")
    _add_listed_minutes(scratch_session, _PDF_DATE, _FILE_URL)
    _add_listed_minutes(scratch_session, _OTHER_DATE, _OTHER_FILE_URL)
    _answer_file(fake_parliament, _FILE_URL, _read_fixture(_PDF_FIXTURE))

    def raise_for_the_second_file(file_url: str) -> MinutesResponse:
        if file_url == _OTHER_FILE_URL:
            raise RuntimeError("second file failed")
        return fake_parliament.get_minutes_file_response(file_url)

    monkeypatch.setattr(
        minutes_step, "get_minutes_file_response", raise_for_the_second_file
    )

    with pytest.raises(RuntimeError):
        minutes_step.populate_minutes(scratch_session, set())

    scratch_session.rollback()
    first_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert first_minutes is not None
    assert first_minutes.status == MinutesStatus.TEXT_STORED
    second_minutes = _get_minutes(scratch_session, _OTHER_DATE)
    assert second_minutes is not None
    assert second_minutes.status == MinutesStatus.LISTED


def test_daily_step_never_touches_file_not_found_or_needs_review(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _add_report(scratch_session, _PDF_DATE, "R1")
    _add_report(scratch_session, _OTHER_DATE, "R2")
    _add_minutes(
        scratch_session,
        Minutes(
            sitting_date=_PDF_DATE,
            status=MinutesStatus.FILE_NOT_FOUND,
            file_url="https://example.test/old.pdf",
        ),
    )
    _add_minutes(
        scratch_session,
        Minutes(
            sitting_date=_OTHER_DATE,
            status=MinutesStatus.NEEDS_REVIEW,
            file_url=_OTHER_FILE_URL,
            status_note="kept",
        ),
    )
    _list_dates(fake_parliament, [_PDF_DATE, _OTHER_DATE])
    _answer_file(fake_parliament, _FILE_URL, _read_fixture(_PDF_FIXTURE))
    _answer_file(fake_parliament, _OTHER_FILE_URL, _read_fixture(_PDF_FIXTURE))

    result = minutes_step.populate_minutes(scratch_session, set())

    not_found_minutes = _get_minutes(scratch_session, _PDF_DATE)
    assert not_found_minutes is not None
    assert not_found_minutes.status == MinutesStatus.FILE_NOT_FOUND
    assert not_found_minutes.file_url == "https://example.test/old.pdf"
    review_minutes = _get_minutes(scratch_session, _OTHER_DATE)
    assert review_minutes is not None
    assert review_minutes.status == MinutesStatus.NEEDS_REVIEW
    assert review_minutes.status_note == "kept"
    assert fake_parliament.minutes_file_calls == []
    assert (result.rows_added, result.rows_listed, result.files_stored) == (0, 0, 0)


def test_index_page_failures_raise_typed_errors(
    scratch_session: Session,
    fake_parliament: FakeParliament,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_parliament.minutes_index_status = _HTTP_NOT_FOUND
    with pytest.raises(HansardMinutesIndexUnavailableError, match="answered 404"):
        minutes_step.populate_minutes(scratch_session, set())
    fake_parliament.minutes_index_status = 200

    monkeypatch.setattr(
        minutes_step,
        "get_minutes_index_response",
        lambda: MinutesResponse(
            url=settings.minutes_index_url, status_code=200, content=b"\xff\xfe"
        ),
    )
    with pytest.raises(HansardMinutesIndexError, match="not UTF-8"):
        minutes_step.populate_minutes(scratch_session, set())

    monkeypatch.setattr(
        minutes_step,
        "get_minutes_index_response",
        fake_parliament.get_minutes_index_response,
    )
    fake_parliament.minutes_index_page = "<html><body></body></html>"
    with pytest.raises(HansardMinutesIndexError, match="initialMPs"):
        minutes_step.populate_minutes(scratch_session, set())

    fake_parliament.minutes_index_error = HansardGatewayError("index down")
    with pytest.raises(HansardGatewayError):
        minutes_step.populate_minutes(scratch_session, set())


def _seed_plan_scenario(
    session: Session, fake_parliament: FakeParliament
) -> tuple[int, set[date]]:
    for report_number, report_date in enumerate(
        (
            _MOVED_DATE,
            _NEW_LISTED_DATE,
            _UNLISTED_DATE,
            _HELD_DATE,
            _STORED_LISTED_DATE,
        )
    ):
        _add_report(session, report_date, f"R{report_number}")
    moved_minutes_id = _add_minutes(
        session, Minutes(sitting_date=_MOVED_DATE, status=MinutesStatus.NOT_YET_LISTED)
    )
    for stored_date in (_HELD_DATE, _STORED_LISTED_DATE):
        _add_listed_minutes(
            session,
            stored_date,
            f"{settings.minutes_media_url}/file-{stored_date.isoformat()}/VP.pdf",
        )
    fake_parliament.minutes_index_page = build_live_index_page(
        [
            build_live_index_row(
                listed_date,
                _FILE_NUMBER,
                f"file-{listed_date.isoformat()}",
                "VP.pdf",
            )
            for listed_date in (
                _MOVED_DATE,
                _NEW_LISTED_DATE,
                _HELD_DATE,
                _NO_REPORT_DATE,
                _STORED_LISTED_DATE,
            )
        ]
    )
    return moved_minutes_id, {_HELD_DATE}


def test_plan_names_every_listing_change_and_file_to_fetch(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    moved_minutes_id, held_sitting_dates = _seed_plan_scenario(
        scratch_session, fake_parliament
    )

    minutes_plan = minutes_step.get_minutes_plan(scratch_session, held_sitting_dates)

    assert minutes_plan.index_page == fake_parliament.minutes_index_page
    assert minutes_plan.listed_sitting_dates == [
        _MOVED_DATE,
        _NEW_LISTED_DATE,
        _HELD_DATE,
        _NO_REPORT_DATE,
        _STORED_LISTED_DATE,
    ]
    assert [index_row.sitting_date for index_row in minutes_plan.new_index_rows] == [
        _NEW_LISTED_DATE,
        _NO_REPORT_DATE,
    ]
    assert [
        (listing_move.minutes_id, listing_move.index_row.sitting_date)
        for listing_move in minutes_plan.listing_moves
    ] == [(moved_minutes_id, _MOVED_DATE)]
    assert minutes_plan.not_yet_listed_dates == [_UNLISTED_DATE]
    assert minutes_plan.file_sitting_dates == [
        _MOVED_DATE,
        _NEW_LISTED_DATE,
        _STORED_LISTED_DATE,
    ]


def test_plan_on_a_read_only_engine_writes_nothing(
    scratch_engine: Engine,
    scratch_session: Session,
    fake_parliament: FakeParliament,
) -> None:
    _, held_sitting_dates = _seed_plan_scenario(scratch_session, fake_parliament)

    with Session(
        scratch_engine.execution_options(postgresql_readonly=True)
    ) as read_only_session:
        minutes_step.get_minutes_plan(read_only_session, held_sitting_dates)

    assert _get_capture_count(scratch_session) == 0
    assert _get_minutes(scratch_session, _UNLISTED_DATE) is None
    assert _get_minutes(scratch_session, _NEW_LISTED_DATE) is None
    moved_minutes = _get_minutes(scratch_session, _MOVED_DATE)
    assert moved_minutes is not None
    assert moved_minutes.status == MinutesStatus.NOT_YET_LISTED
    assert fake_parliament.minutes_file_calls == []


def test_step_fetches_exactly_the_files_the_plan_names(
    scratch_session: Session, fake_parliament: FakeParliament
) -> None:
    _, held_sitting_dates = _seed_plan_scenario(scratch_session, fake_parliament)
    minutes_plan = minutes_step.get_minutes_plan(scratch_session, held_sitting_dates)
    assert minutes_plan.file_sitting_dates

    minutes_step.populate_minutes(scratch_session, held_sitting_dates)

    assert sorted(fake_parliament.minutes_file_calls) == sorted(
        f"{settings.minutes_media_url}/file-{file_sitting_date.isoformat()}/VP.pdf"
        for file_sitting_date in minutes_plan.file_sitting_dates
    )
