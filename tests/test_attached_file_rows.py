import json
from pathlib import Path

import pytest

from enums import AttachedFileKind
from exceptions import HansardAttachedFileError
from services.attached_file import build_attached_files, get_annexure_entries

_SITTING_ID = 7
_ANNEX_LIST_ID = 4101
_VERNACULAR_LIST_ID = 8201
_LIST_ENTRIES_PATH = (
    Path(__file__).parent / "fixtures" / "attached_files" / "list_entries.json"
)


def _get_list_text(case_name: str) -> str:
    return json.dumps(json.loads(_LIST_ENTRIES_PATH.read_text())[case_name])


def test_annex_and_vernacular_rows_get_kind_title_path_and_download_value() -> None:
    attached_files = build_attached_files(
        _SITTING_ID, _get_list_text("annexures"), _get_list_text("vernaculars")
    )

    annex, vernacular = attached_files
    assert annex.kind == AttachedFileKind.ANNEX
    assert annex.sprs_file_id == _ANNEX_LIST_ID
    assert annex.printed_title == "Annex to the Committee of Supply debate"
    assert (
        annex.printed_file_path
        == "d:/apps/reports/solr_files/20230301/annex-Committee of Supply.pdf"
    )
    assert annex.download_value == "20230301/annex-Committee of Supply.pdf"
    assert annex.section_type == "OS"
    assert annex.sitting_id == _SITTING_ID
    assert vernacular.kind == AttachedFileKind.VERNACULAR
    assert vernacular.sprs_file_id == _VERNACULAR_LIST_ID
    assert vernacular.download_value == "20160816/vernacular-Thomas Chua(4).pdf"
    assert vernacular.section_type is None


def test_null_lists_give_no_rows() -> None:
    assert build_attached_files(_SITTING_ID, None, None) == []


def test_placeholder_path_gets_no_download_value() -> None:
    attached_files = build_attached_files(
        _SITTING_ID, None, _get_list_text("placeholder")
    )

    assert len(attached_files) == 1
    assert attached_files[0].download_value is None
    assert (
        attached_files[0].printed_file_path
        == "d:/apps/reports/solr_files/20170801/vernacular-null"
    )


def test_identical_entries_give_one_row_with_the_lowest_list_id() -> None:
    attached_files = build_attached_files(
        _SITTING_ID, None, _get_list_text("duplicates")
    )

    assert [attached_file.sprs_file_id for attached_file in attached_files] == [8401]


def test_placeholders_with_different_titles_stay_two_rows() -> None:
    attached_files = build_attached_files(
        _SITTING_ID, None, _get_list_text("placeholders_with_different_titles")
    )

    assert [attached_file.sprs_file_id for attached_file in attached_files] == [
        8501,
        8502,
    ]


def test_list_missing_file_path_raises_naming_the_list_and_the_key() -> None:
    with pytest.raises(HansardAttachedFileError, match="annexureList.*filePath"):
        build_attached_files(_SITTING_ID, _get_list_text("missing_file_path"), None)


def test_file_path_without_the_marker_raises_naming_the_list_and_the_key() -> None:
    with pytest.raises(HansardAttachedFileError, match="annexureList.*filePath"):
        build_attached_files(_SITTING_ID, _get_list_text("path_without_marker"), None)


def test_annexure_without_section_type_parses_with_none() -> None:
    annexure_entries = get_annexure_entries(
        _get_list_text("annexure_without_section_type")
    )

    assert annexure_entries[0].section_type is None
