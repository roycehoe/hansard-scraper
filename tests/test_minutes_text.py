import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from enums import MinutesFileFormat
from exceptions import HansardMinutesFileError
from services import minutes_text
from services.minutes_text import (
    get_minutes_file_format,
    get_minutes_pdf_text,
    get_minutes_word_text,
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

    with pytest.raises(HansardMinutesFileError, match="The PDF cannot be read") as caught:
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
        get_minutes_word_text(_read_fixture_bytes(_WORD_FIXTURE)[:_TRUNCATED_WORD_BYTES])
