from pathlib import Path

from crud.speech import SpeechRow
from enums import AttachedFilePointerShape, ParagraphTieRule
from services.attached_file import (
    build_attached_file_pointers,
    get_bad_file_link_count,
)

_SPRS_REPORT_ID = "report-1#"
_REPORT_LINKS_PATH = (
    Path(__file__).parent / "fixtures" / "attached_files" / "report_links.html"
)
_BAD_FILE_LINK_COUNT = 2


def _get_report_links() -> str:
    return _REPORT_LINKS_PATH.read_text()


def test_each_pointer_gets_its_shape_value_and_position() -> None:
    pointers = build_attached_file_pointers(_SPRS_REPORT_ID, _get_report_links(), [])

    assert [pointer.ordinal for pointer in pointers] == [1, 2, 3, 4, 5, 6, 7]
    annex, vernacular, pdfs, section_file, htm, trailing, placeholder = pointers
    assert annex.shape == AttachedFilePointerShape.DATED
    assert annex.download_value == "20230301/annex-Committee of Supply.pdf"
    assert annex.href == (
        "/search/search/download?value=20230301/annex-Committee of Supply.pdf"
    )
    assert annex.sprs_report_id == _SPRS_REPORT_ID
    assert vernacular.shape == AttachedFilePointerShape.DATED
    assert vernacular.download_value == "20160816/vernacular-Thomas Chua(4).pdf"
    assert pdfs.shape == AttachedFilePointerShape.PDFS
    assert pdfs.download_value == "PDFs/Reply to Question 12.pdf"
    assert section_file.shape == AttachedFilePointerShape.SECTION_FILE
    assert section_file.download_value == "12_20230301_S0003_T0007.pdf"
    assert section_file.href.startswith("https://sprs.parl.gov.sg/")
    assert htm.shape == AttachedFilePointerShape.PDFS
    assert htm.download_value == "PDFs/Annex B.htm"
    assert trailing.download_value == "PDFs/Trailing Space.pdf "
    assert placeholder.shape == AttachedFilePointerShape.DATED


def test_links_that_are_not_file_pointers_are_left_out() -> None:
    pointers = build_attached_file_pointers(_SPRS_REPORT_ID, _get_report_links(), [])

    hrefs = [pointer.href for pointer in pointers]
    assert "#fnsrc_1" not in hrefs
    assert "mailto:feedback@parl.gov.sg" not in hrefs
    assert "http://www.example.gov.sg/page" not in hrefs
    assert "530" not in hrefs
    assert "." not in hrefs
    assert all("download?value=" in href for href in hrefs)


def test_placeholder_link_keeps_its_href_and_gets_no_download_value() -> None:
    pointers = build_attached_file_pointers(_SPRS_REPORT_ID, _get_report_links(), [])

    placeholder = pointers[-1]
    assert placeholder.href == (
        "/search/search/download?value=20170801/vernacular-null"
    )
    assert placeholder.download_value is None


def test_printed_text_keeps_a_leading_space_as_printed() -> None:
    pointers = build_attached_file_pointers(_SPRS_REPORT_ID, _get_report_links(), [])

    assert pointers[-1].printed_text == " Vernacular Speech"
    assert pointers[0].printed_text == "Annex A"


def test_no_content_gives_no_rows() -> None:
    assert build_attached_file_pointers(_SPRS_REPORT_ID, None, []) == []


def test_bad_file_link_count_counts_numbered_and_dot_links_naming_a_file() -> None:
    assert get_bad_file_link_count(_get_report_links()) == _BAD_FILE_LINK_COUNT
    assert get_bad_file_link_count(None) == 0


def _get_speech_row(ordinal: int, transcript: str) -> SpeechRow:
    return SpeechRow(
        id=ordinal,
        ordinal=ordinal,
        speaker=None,
        transcript=transcript,
        report_id=1,
        speaker_id=None,
    )


def _get_link(text: str, value: str = "PDFs/a.pdf") -> str:
    return f'<a href="/search/search/download?value={value}">{text}</a>'


def test_one_occurrence_ties_to_its_row_with_only_occurrence() -> None:
    content = f"<p>Please see {_get_link('Vernacular Speech')} here.</p>"
    speech_rows = [
        _get_speech_row(1, "Opening remarks."),
        _get_speech_row(2, "Please see Vernacular Speech here."),
    ]

    (pointer,) = build_attached_file_pointers(_SPRS_REPORT_ID, content, speech_rows)

    assert pointer.speech_ordinal == speech_rows[1].ordinal
    assert pointer.paragraph_tie_rule == ParagraphTieRule.ONLY_OCCURRENCE


def test_two_links_with_the_same_words_tie_in_order_to_every_occurrence() -> None:
    content = (
        f"<p>{_get_link('Vernacular Speech', 'PDFs/a.pdf')}</p>\n"
        f"<p>{_get_link('Vernacular Speech', 'PDFs/b.pdf')}</p>"
    )
    speech_rows = [
        _get_speech_row(3, "Vernacular Speech"),
        _get_speech_row(4, "Vernacular Speech"),
    ]

    first, second = build_attached_file_pointers(_SPRS_REPORT_ID, content, speech_rows)

    assert (first.speech_ordinal, second.speech_ordinal) == (3, 4)
    assert first.paragraph_tie_rule == ParagraphTieRule.EVERY_OCCURRENCE_A_LINK
    assert second.paragraph_tie_rule == ParagraphTieRule.EVERY_OCCURRENCE_A_LINK


def test_plain_text_before_two_links_gives_occurrence_beside_plain_text() -> None:
    content = (
        "<p>The Vernacular Speech follows.</p>\n"
        f"<p>{_get_link('Vernacular Speech', 'PDFs/a.pdf')}</p>\n"
        f"<p>{_get_link('Vernacular Speech', 'PDFs/b.pdf')}</p>"
    )
    speech_rows = [
        _get_speech_row(1, "The Vernacular Speech follows."),
        _get_speech_row(2, "Vernacular Speech"),
        _get_speech_row(3, "Vernacular Speech"),
    ]

    first, second = build_attached_file_pointers(_SPRS_REPORT_ID, content, speech_rows)

    assert (first.speech_ordinal, second.speech_ordinal) == (2, 3)
    assert first.paragraph_tie_rule == ParagraphTieRule.OCCURRENCE_BESIDE_PLAIN_TEXT
    assert second.paragraph_tie_rule == ParagraphTieRule.OCCURRENCE_BESIDE_PLAIN_TEXT


def test_a_link_that_is_not_a_pointer_counts_as_plain_text() -> None:
    content = (
        '<p><a href="530">Vernacular Speech</a></p>\n'
        f"<p>{_get_link('Vernacular Speech')}</p>"
    )
    speech_rows = [
        _get_speech_row(1, "Vernacular Speech"),
        _get_speech_row(2, "Vernacular Speech"),
    ]

    (pointer,) = build_attached_file_pointers(_SPRS_REPORT_ID, content, speech_rows)

    assert pointer.speech_ordinal == speech_rows[1].ordinal
    assert pointer.paragraph_tie_rule == ParagraphTieRule.OCCURRENCE_BESIDE_PLAIN_TEXT


def test_counts_that_differ_give_no_tie() -> None:
    content = f"<p>{_get_link('Vernacular Speech')}</p>"
    speech_rows = [_get_speech_row(1, "Some other words.")]

    (pointer,) = build_attached_file_pointers(_SPRS_REPORT_ID, content, speech_rows)

    assert pointer.speech_ordinal is None
    assert pointer.paragraph_tie_rule is None


def test_empty_words_give_no_tie() -> None:
    content = f"<p>{_get_link('')}</p>"
    speech_rows = [_get_speech_row(1, "Some words.")]

    (pointer,) = build_attached_file_pointers(_SPRS_REPORT_ID, content, speech_rows)

    assert pointer.speech_ordinal is None
    assert pointer.paragraph_tie_rule is None


def test_markers_no_break_spaces_and_zero_width_spaces_do_not_stop_a_match() -> None:
    content = f"<p>{_get_link('Vernacular Speech')}</p>"
    speech_rows = [_get_speech_row(5, "__Vernac​ular\xa0Speech__")]

    (pointer,) = build_attached_file_pointers(_SPRS_REPORT_ID, content, speech_rows)

    assert pointer.speech_ordinal == speech_rows[0].ordinal
    assert pointer.paragraph_tie_rule == ParagraphTieRule.ONLY_OCCURRENCE


def test_a_pointer_nested_in_another_leaves_no_marker_in_either_printed_text() -> None:
    content = (
        '<a href="/search/search/download?value=PDFs/A.pdf">A'
        '<a href="/search/search/download?value=PDFs/B.pdf">B</a>'
    )

    outer, inner = build_attached_file_pointers(_SPRS_REPORT_ID, content, [])

    assert outer.printed_text == "AB"
    assert inner.printed_text == "B"
    assert all(
        "\x01" not in pointer.printed_text and "\x02" not in pointer.printed_text
        for pointer in (outer, inner)
    )
