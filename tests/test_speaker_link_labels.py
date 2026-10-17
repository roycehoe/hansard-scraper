from typing import Optional

import pytest

from database.speaker import Speaker
from populate.speaker_links import _resolve_speech_speaker_id
from services.attendance import build_speaker_lookups

_PARTY = "People's Action Party"
_SPEAKERS = (
    Speaker(id=1, name="Yeoh Ghim Seng", party=_PARTY, is_legislative_assembly=False, parliament_number=6),
    Speaker(id=2, name="Teo Chee Hean", party=_PARTY, is_legislative_assembly=False, parliament_number=9),
    Speaker(id=3, name="Teh Cheang Wan", party=_PARTY, is_legislative_assembly=False, parliament_number=5),
    Speaker(id=4, name="Desmond Choo", party=_PARTY, is_legislative_assembly=False, parliament_number=13),
    Speaker(id=5, name="David Marshall", party="Labour Front", is_legislative_assembly=True, parliament_number=0),
    Speaker(id=6, name="Ng Eng Hen", party=_PARTY, is_legislative_assembly=False, parliament_number=10),
)
_LOOKUPS = build_speaker_lookups(list(_SPEAKERS))
_NAME_AND_PARLIAMENT_TO_SPEAKER_ID = {(speaker.name, speaker.parliament_number): speaker.id for speaker in _SPEAKERS}


@pytest.mark.parametrize(
    ("label", "parliament", "expected_speaker_id"),
    [
        ("Dr Yeoh Ghim Seng (Mr Speaker)", 6, 1),
        ("MR TEO CHEE HEAN", 9, 2),
        ("Mr Teh Cheang Won", 5, 3),
        ("Mr Desmond Choo –", 13, 4),
        ('"Mr David Marshall', 0, 5),
        ("Dr Ng Eng Hen.", 10, 6),
    ],
)
def test_label_that_names_a_member_links_to_that_member(label: str, parliament: int, expected_speaker_id: Optional[int]) -> None:
    speaker_id = _resolve_speech_speaker_id(label, parliament, None, _LOOKUPS, _NAME_AND_PARLIAMENT_TO_SPEAKER_ID)

    assert speaker_id == expected_speaker_id
