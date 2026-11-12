import io
from datetime import date
from pathlib import Path

import pytest
from pypdf import PdfWriter

from enums import MinutesFileFormat, MinutesStatus
from exceptions import HansardMinutesFileError
from services import minutes_text
from services.minutes_text import (
    get_minutes_file_format,
    get_minutes_head_dates,
    get_minutes_pdf_text,
    get_minutes_text_outcome,
    get_minutes_word_text,
    is_minutes_head,
)

_FIXTURE_DIRECTORY = Path(__file__).parent / "division_fixtures" / "minutes"
_PDF_FIXTURE = "vp-10jan18-first-pages.pdf"
_WORD_FIXTURE = "vp0592008_7.doc"
_BLANK_PAGE_SIZE = 200
_TRUNCATED_PDF_BYTES = 500
_TRUNCATED_WORD_BYTES = 2_000
_DIVISION_SPELLED_ABSTENTION = "a division was taken: Ayes 75, Noes 0, Abstention 0"
_DIVISION_MISPRINTED_ABSENTION = "a division was taken: Ayes 75, Noes 0, Absention 0"
_DIVISION_PREFIX = "a division was taken: Ayes 75, Noes 0, Abs"
_EXPECTED_DIVISION_COUNT = 2


def _read_fixture_bytes(name: str) -> bytes:
    return (_FIXTURE_DIRECTORY / name).read_bytes()


def _build_blank_pdf(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=_BLANK_PAGE_SIZE, height=_BLANK_PAGE_SIZE)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _raise_value_error(content: object) -> None:
    raise ValueError("damaged")


def _raise_key_error(content: object) -> None:
    raise KeyError("/Root")


def _raise_index_error(content: object) -> None:
    raise IndexError("no page")


def _raise_type_error(content: object) -> None:
    raise TypeError("our bug")


def test_pdf_signature_is_a_pdf() -> None:
    assert get_minutes_file_format(_read_fixture_bytes(_PDF_FIXTURE)) == (
        MinutesFileFormat.PDF
    )


def test_ole2_signature_is_word() -> None:
    assert get_minutes_file_format(_read_fixture_bytes(_WORD_FIXTURE)) == (
        MinutesFileFormat.WORD
    )


@pytest.mark.parametrize("content", [b"PK\x03\x04 a docx", b""])
def test_unknown_signature_raises(content: bytes) -> None:
    with pytest.raises(HansardMinutesFileError):
        get_minutes_file_format(content)


def test_pdf_text_holds_the_head_of_the_file() -> None:
    text = get_minutes_pdf_text(_read_fixture_bytes(_PDF_FIXTURE))

    assert "WEDNESDAY, 10 JANUARY 2018" in text
    assert "VOTES AND PROCEEDINGS" in text


def test_blank_page_pdf_raises() -> None:
    with pytest.raises(HansardMinutesFileError, match="holds no text"):
        get_minutes_pdf_text(_build_blank_pdf(1))


def test_pdf_with_a_blank_second_page_raises() -> None:
    writer = PdfWriter()
    writer.append(io.BytesIO(_read_fixture_bytes(_PDF_FIXTURE)), pages=(0, 1))
    writer.add_blank_page(width=_BLANK_PAGE_SIZE, height=_BLANK_PAGE_SIZE)
    buffer = io.BytesIO()
    writer.write(buffer)

    with pytest.raises(HansardMinutesFileError, match="PDF page 2 holds no text"):
        get_minutes_pdf_text(buffer.getvalue())


@pytest.mark.parametrize(
    "raise_error", [_raise_value_error, _raise_key_error, _raise_index_error]
)
def test_pdf_reader_value_key_and_index_errors_become_minutes_file_errors(
    raise_error: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(minutes_text, "PdfReader", raise_error)

    with pytest.raises(
        HansardMinutesFileError, match="The PDF cannot be read"
    ) as caught:
        get_minutes_pdf_text(_read_fixture_bytes(_PDF_FIXTURE))

    assert caught.value.__cause__ is not None


def test_pdf_reader_type_error_is_not_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(minutes_text, "PdfReader", _raise_type_error)

    with pytest.raises(TypeError):
        get_minutes_pdf_text(_read_fixture_bytes(_PDF_FIXTURE))


def test_pdf_with_no_pages_raises() -> None:
    with pytest.raises(HansardMinutesFileError, match="holds no pages"):
        get_minutes_pdf_text(_build_blank_pdf(0))


def test_truncated_pdf_raises() -> None:
    with pytest.raises(HansardMinutesFileError):
        get_minutes_pdf_text(_read_fixture_bytes(_PDF_FIXTURE)[:_TRUNCATED_PDF_BYTES])


def test_word_text_holds_both_divisions_of_the_sample() -> None:
    text = get_minutes_word_text(_read_fixture_bytes(_WORD_FIXTURE))

    assert "TUESDAY, 21ST OCTOBER, 2008" in text
    assert text.count(_DIVISION_PREFIX) == _EXPECTED_DIVISION_COUNT
    assert text.count(_DIVISION_MISPRINTED_ABSENTION) == 1
    assert text.count(_DIVISION_SPELLED_ABSTENTION) == 1


def test_word_file_that_is_cut_short_raises() -> None:
    with pytest.raises(HansardMinutesFileError):
        get_minutes_word_text(
            _read_fixture_bytes(_WORD_FIXTURE)[:_TRUNCATED_WORD_BYTES]
        )


def test_head_dates_of_the_pdf_and_word_samples() -> None:
    pdf_text = get_minutes_pdf_text(_read_fixture_bytes(_PDF_FIXTURE))
    word_text = get_minutes_word_text(_read_fixture_bytes(_WORD_FIXTURE))

    assert get_minutes_head_dates(pdf_text) == [date(2018, 1, 10)]
    assert get_minutes_head_dates(word_text) == [date(2008, 10, 21)]


def test_head_date_reads_ordinal_suffix_and_comma() -> None:
    assert get_minutes_head_dates("TUESDAY, 21ST OCTOBER, 2008") == [date(2008, 10, 21)]


def test_head_date_ignores_an_impossible_month() -> None:
    assert get_minutes_head_dates("MONDAY, 4 OCTOBRE 2021") == []


def test_head_title_matches_ignoring_case() -> None:
    assert is_minutes_head("Votes And Proceedings")
    assert is_minutes_head("VOTES   AND PROCEEDINGS")
    assert not is_minutes_head("keith chua cv")


def test_outcome_agrees_when_the_head_date_is_the_sitting_date() -> None:
    outcome = get_minutes_text_outcome(date(2018, 1, 10), "WEDNESDAY, 10 JANUARY 2018")

    assert outcome.status == MinutesStatus.TEXT_STORED
    assert outcome.status_note is None


def test_outcome_needs_review_when_the_head_prints_another_date() -> None:
    outcome = get_minutes_text_outcome(date(2018, 1, 11), "WEDNESDAY, 10 JANUARY 2018")

    assert outcome.status == MinutesStatus.NEEDS_REVIEW
    assert outcome.status_note == (
        "The file's head prints 10 January 2018, not the sitting date"
    )


def test_outcome_stores_text_when_the_head_prints_no_date() -> None:
    outcome = get_minutes_text_outcome(date(2018, 1, 10), "no date here")

    assert outcome.status == MinutesStatus.TEXT_STORED
    assert outcome.status_note is None
