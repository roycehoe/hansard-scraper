import json
from pathlib import Path

import pytest

from services.speech import get_speeches, get_start_of_speech_line
from utils.markdown_parser import get_cleaned_report_markdown

_FIXTURE_PATHS = sorted((Path(__file__).parent / "fixtures").glob("*.json"))


@pytest.mark.parametrize("fixture_path", _FIXTURE_PATHS, ids=lambda fixture_path: fixture_path.stem)
def test_speeches_match_golden_fixture(fixture_path: Path) -> None:
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

    assert [[speech.speaker, speech.transcript, speech.kind] for speech in speeches] == fixture["expected_rows"]
