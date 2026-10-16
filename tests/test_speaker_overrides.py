import json
from pathlib import Path

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from schemas.speaker import SpeakerResult
from schemas.speaker_override import SpeakerOverrides
from services.speaker import build_speaker

_DATA_FILE = Path(__file__).parent.parent / "data" / "speaker_overrides.json"


def test_override_replaces_the_scraped_flag() -> None:
    speaker_result = SpeakerResult(name="Lee Kuan Yew", party="People's Action Party", is_legislative_assembly=True, parliament_number=2)

    speaker = build_speaker(speaker_result, {("Lee Kuan Yew", 2): False})

    assert speaker.is_legislative_assembly is False


def test_row_without_an_override_keeps_the_scraped_flag() -> None:
    speaker_result = SpeakerResult(name="Lee Kuan Yew", party="People's Action Party", is_legislative_assembly=True, parliament_number=1)

    speaker = build_speaker(speaker_result, {("Lee Kuan Yew", 2): False})

    assert speaker.is_legislative_assembly is True


def test_data_file_names_each_membership_once_and_changes_its_flag() -> None:
    overrides = SpeakerOverrides.model_validate(json.loads(_DATA_FILE.read_text())).legislative_assembly_overrides

    keys = [(override.name, override.parliament_number) for override in overrides]
    assert len(keys) == len(set(keys))
    assert all(override.source_is_legislative_assembly != override.is_legislative_assembly for override in overrides)
