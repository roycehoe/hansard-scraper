from datetime import datetime
from typing import Optional

import pytest

from database.speaker import Speaker
from services.attendance import build_speaker_lookups
from services.speaker_link import _resolve_speech_speaker_id

_PARTY = "People's Action Party"
_SPEAKERS = (
    Speaker(id=1, name="Yeoh Ghim Seng", party=_PARTY, is_legislative_assembly=False, parliament_number=6),
    Speaker(id=2, name="Teo Chee Hean", party=_PARTY, is_legislative_assembly=False, parliament_number=9),
    Speaker(id=3, name="Teh Cheang Wan", party=_PARTY, is_legislative_assembly=False, parliament_number=5),
    Speaker(id=4, name="Desmond Choo", party=_PARTY, is_legislative_assembly=False, parliament_number=13),
    Speaker(id=5, name="David Marshall", party="Labour Front", is_legislative_assembly=True, parliament_number=0),
    Speaker(id=6, name="Ng Eng Hen", party=_PARTY, is_legislative_assembly=False, parliament_number=10),
    Speaker(id=7, name="Seah Kian Peng", party=_PARTY, is_legislative_assembly=False, parliament_number=15),
    Speaker(id=8, name="Masagos Zulkifli Bin Masagos Mohamad", party=_PARTY, is_legislative_assembly=False, parliament_number=15),
    Speaker(id=9, name="Kenneth Tiong", party="Workers' Party", is_legislative_assembly=False, parliament_number=15),
    Speaker(id=10, name="Tan Chuan-Jin", party=_PARTY, is_legislative_assembly=False, parliament_number=13),
    Speaker(id=11, name="Rahmat Bin Kenap", party=_PARTY, is_legislative_assembly=True, parliament_number=1),
    Speaker(id=12, name="Mohd Ali Bin Alwi", party=_PARTY, is_legislative_assembly=True, parliament_number=0),
    Speaker(id=13, name="Foo Mee Har", party=_PARTY, is_legislative_assembly=False, parliament_number=12),
)
_LOOKUPS = build_speaker_lookups(list(_SPEAKERS))
_NAME_AND_PARLIAMENT_TO_SPEAKER_ID = {(speaker.name, speaker.parliament_number): speaker.id for speaker in _SPEAKERS}


@pytest.mark.parametrize(
    ("label", "parliament", "expected_speaker_id"),
    [
        ("Inche Mohd. Ali Bin Alwi Kampong Kembangan)", 0, 12),
        ("Ms Foo Mee Har West Coast)", 12, 13),
        ("Dr Yeoh Ghim Seng (Mr Speaker)", 6, 1),
        ("MR TEO CHEE HEAN", 9, 2),
        ("Mr Teh Cheang Won", 5, 3),
        ("Mr Desmond Choo –", 13, 4),
        ('"Mr David Marshall', 0, 5),
        ("Dr Ng Eng Hen.", 10, 6),
        ("Mr Masagos Zulkifli B M M", 15, 8),
        ("The Minister for Social and Family Development (Mr Masagos Zulkifli B M M)", 15, 8),
        ("Mr Kenneth Tiong Boon Kiat (Aljunied)", 15, 9),
        ("Mr Kenneth Tiong Boon Kiat", 15, 9),
        ("Inche Rahamat", 1, 11),
    ],
)
def test_label_that_names_a_member_links_to_that_member(label: str, parliament: int, expected_speaker_id: Optional[int]) -> None:
    speaker_id = _resolve_speech_speaker_id(label, parliament, None, _LOOKUPS, _NAME_AND_PARLIAMENT_TO_SPEAKER_ID)

    assert speaker_id == expected_speaker_id


def test_speaker_label_in_the_15th_parliament_links_to_the_speaker() -> None:
    speaker_id = _resolve_speech_speaker_id("Mr Speaker", 15, datetime(2026, 10, 6), _LOOKUPS, _NAME_AND_PARLIAMENT_TO_SPEAKER_ID)

    assert speaker_id == _NAME_AND_PARLIAMENT_TO_SPEAKER_ID[("Seah Kian Peng", 15)]


def test_speaker_label_in_the_13th_parliament_links_to_the_speaker_of_the_day() -> None:
    speaker_id = _resolve_speech_speaker_id("Mr Speaker", 13, datetime(2019, 5, 8), _LOOKUPS, _NAME_AND_PARLIAMENT_TO_SPEAKER_ID)

    assert speaker_id == _NAME_AND_PARLIAMENT_TO_SPEAKER_ID[("Tan Chuan-Jin", 13)]
