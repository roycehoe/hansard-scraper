import json
from pathlib import Path

import pytest

from services.speech import get_speeches, get_start_of_speech_line
from utils.column_numbers import (
    ColumnRange,
    SpeechColumn,
    SpeechText,
    build_column_text,
    get_column_markers,
    get_head_column_range,
    get_report_column_range,
    get_speech_columns,
)
from utils.markdown_parser import get_cleaned_report_markdown

_FIXTURE_PATHS = sorted((Path(__file__).parent / "fixtures" / "columns").glob("*.json"))


def _get_speech_columns(report_html: str, speech_texts: list[SpeechText]) -> list[SpeechColumn]:
    column_text = build_column_text(report_html)
    return get_speech_columns(column_text, get_column_markers(column_text), get_head_column_range(report_html), speech_texts)


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
    column_markers = get_column_markers(column_text)
    head_column_range = get_head_column_range(fixture["html"])
    speech_columns = get_speech_columns(column_text, column_markers, head_column_range, [SpeechText(speech.speaker, speech.transcript) for speech in speeches])

    expected_column_range = None if fixture["expected_column_range"] is None else ColumnRange(*fixture["expected_column_range"])
    assert get_report_column_range(column_markers, head_column_range) == expected_column_range
    assert [speech_column.column_start for speech_column in speech_columns] == fixture["expected_start_columns"]
    column_notes = {
        str(i): [speech_column.column_note, speech_column.column_suggested]
        for i, speech_column in enumerate(speech_columns)
        if speech_column.column_note is not None
    }
    assert column_notes == fixture.get("expected_column_notes", {})


def test_text_before_the_first_marker_has_no_column() -> None:
    speech_columns = _get_speech_columns(
        "<p>Sir, the answer is no.</p><p>Column: 12</p><p>Yes.</p>",
        [SpeechText(None, "Sir, the answer is no."), SpeechText(None, "Yes.")],
    )

    assert [speech_column.column_start for speech_column in speech_columns] == [None, 12]


def test_report_without_markers_has_no_range() -> None:
    column_text = build_column_text("<p>Page: 4</p><p>Sir, the answer is no.</p>")

    assert get_report_column_range(get_column_markers(column_text), None) is None
