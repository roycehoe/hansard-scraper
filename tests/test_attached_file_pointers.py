from pathlib import Path

from enums import AttachedFilePointerShape
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
