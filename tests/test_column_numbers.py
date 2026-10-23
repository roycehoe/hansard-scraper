import json
from pathlib import Path

import pytest

from services.speech import get_speeches, get_start_of_speech_line
from utils.column_numbers import (
    ColumnRange,
    build_column_text,
    get_report_column_range,
    get_speech_start_columns,
)
from utils.markdown_parser import get_cleaned_report_markdown

_FIXTURE_PATHS = sorted((Path(__file__).parent / "fixtures" / "columns").glob("*.json"))


@pytest.mark.parametrize("fixture_path", _FIXTURE_PATHS, ids=lambda fixture_path: fixture_path.stem)
def test_columns_match_fixture(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    markdown = get_cleaned_report_markdown(fixture["html"], fixture["report_version"])
    start_of_speech_line = get_start_of_speech_line(
        markdown,
        fixture["title"],
        fixture["subtitle"],
        fixture["original_title"],
        fixture["report_type"],
        fixture["report_version"],
    )
    assert start_of_speech_line is not None
    speeches = get_speeches(markdown, start_of_speech_line, fixture["report_type"], fixture["report_version"])

    column_text = build_column_text(fixture["html"])

    assert get_report_column_range(column_text) == ColumnRange(*fixture["expected_column_range"])
    assert get_speech_start_columns(column_text, [speech.transcript for speech in speeches]) == fixture["expected_start_columns"]


def test_text_before_the_first_marker_has_no_column() -> None:
    column_text = build_column_text("<p>Sir, the answer is no.</p><p>Column: 12</p><p>Yes.</p>")

    assert get_speech_start_columns(column_text, ["Sir, the answer is no.", "Yes."]) == [None, 12]


def test_report_without_markers_has_no_range() -> None:
    assert get_report_column_range(build_column_text("<p>Page: 4</p><p>Sir, the answer is no.</p>")) is None
