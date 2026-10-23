import pytest

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from database.speaker import Speaker
from exceptions import HansardWriteCheckError
from schemas.hand_kept_member import HandKeptMember
from schemas.speaker import SpeakerResult
from schemas.speaker_override import PartyOverride
from services.speaker import PartyChange, build_speaker, get_party_changes
from utils.data_files import get_colonial_members, get_speaker_overrides

_CURLY_APOSTROPHE = "’"


def _get_speaker(speaker_id: int, name: str, parliament_number: int, party: str) -> Speaker:
    return Speaker(id=speaker_id, name=name, party=party, is_legislative_assembly=False, parliament_number=parliament_number)


def test_override_replaces_the_scraped_flag() -> None:
    speaker_result = SpeakerResult(name="Lee Kuan Yew", party="People's Action Party", is_legislative_assembly=True, parliament_number=2)

    speaker = build_speaker(speaker_result, {("Lee Kuan Yew", 2): False}, {})

    assert speaker.is_legislative_assembly is False


def test_row_without_an_override_keeps_the_scraped_flag() -> None:
    speaker_result = SpeakerResult(name="Lee Kuan Yew", party="People's Action Party", is_legislative_assembly=True, parliament_number=1)

    speaker = build_speaker(speaker_result, {("Lee Kuan Yew", 2): False}, {})

    assert speaker.is_legislative_assembly is True


def test_data_file_names_each_membership_once_and_changes_its_flag() -> None:
    overrides = get_speaker_overrides().legislative_assembly_overrides

    keys = [(override.name, override.parliament_number) for override in overrides]
    assert len(keys) == len(set(keys))
    assert all(override.source_is_legislative_assembly != override.is_legislative_assembly for override in overrides)


def test_override_replaces_the_scraped_party() -> None:
    speaker_result = SpeakerResult(name="Chiam See Tong", party="Singapore Democratic Alliance", is_legislative_assembly=False, parliament_number=6)

    speaker = build_speaker(speaker_result, {}, {("Chiam See Tong", 6): "Singapore Democratic Party"})

    assert speaker.party == "Singapore Democratic Party"


def test_row_without_a_party_override_keeps_the_scraped_party() -> None:
    speaker_result = SpeakerResult(name="Chiam See Tong", party="Singapore Democratic Alliance", is_legislative_assembly=False, parliament_number=10)

    speaker = build_speaker(speaker_result, {}, {("Chiam See Tong", 6): "Singapore Democratic Party"})

    assert speaker.party == "Singapore Democratic Alliance"


def test_curly_apostrophe_in_the_scraped_party_becomes_straight() -> None:
    speaker_result = SpeakerResult(name="Charles Chong", party=f"People{_CURLY_APOSTROPHE}s Action Party", is_legislative_assembly=False, parliament_number=7)

    speaker = build_speaker(speaker_result, {}, {})

    assert speaker.party == "People's Action Party"


def test_party_override_data_file_names_each_membership_once_and_changes_its_party() -> None:
    overrides = get_speaker_overrides().party_overrides

    keys = [(override.name, override.parliament_number) for override in overrides]
    assert len(keys) == len(set(keys))
    assert all(override.source_party != override.party for override in overrides)
    assert all(_CURLY_APOSTROPHE not in override.party for override in overrides)


def test_colonial_members_hold_no_placeholder_or_curly_party_and_no_overridden_key() -> None:
    members = get_colonial_members()
    overrides = get_speaker_overrides().party_overrides

    assert all(member.party != "Unknown" for member in members)
    assert all(_CURLY_APOSTROPHE not in member.party for member in members)
    member_keys = {(member.name, member.parliament_number) for member in members}
    assert not member_keys & {(override.name, override.parliament_number) for override in overrides}


def test_party_changes_cover_overrides_colonial_members_and_curly_apostrophes() -> None:
    speakers = [
        _get_speaker(1, "Chiam See Tong", 6, "Singapore Democratic Alliance"),
        _get_speaker(2, "Lim Yew Hock", 1, "Labour Front"),
        _get_speaker(3, "Charles Chong", 7, f"People{_CURLY_APOSTROPHE}s Action Party"),
        _get_speaker(4, "Lee Hsien Loong", 7, "People's Action Party"),
    ]
    overrides = [PartyOverride(name="Chiam See Tong", parliament_number=6, source_party="Singapore Democratic Alliance", party="Singapore Democratic Party", reason="test")]
    colonial_members = [HandKeptMember(name="Lim Yew Hock", party="Singapore People's Alliance", is_legislative_assembly=True, parliament_number=1, comments=None)]

    party_changes = get_party_changes(speakers, overrides, colonial_members)

    assert party_changes == [
        PartyChange(1, "Chiam See Tong", 6, "Singapore Democratic Alliance", "Singapore Democratic Party"),
        PartyChange(2, "Lim Yew Hock", 1, "Labour Front", "Singapore People's Alliance"),
        PartyChange(3, "Charles Chong", 7, f"People{_CURLY_APOSTROPHE}s Action Party", "People's Action Party"),
    ]


def test_party_changes_are_empty_once_applied() -> None:
    speakers = [_get_speaker(1, "Chiam See Tong", 6, "Singapore Democratic Party")]
    overrides = [PartyOverride(name="Chiam See Tong", parliament_number=6, source_party="Singapore Democratic Alliance", party="Singapore Democratic Party", reason="test")]

    assert get_party_changes(speakers, overrides, []) == []


def test_party_override_for_a_missing_row_raises() -> None:
    overrides = [PartyOverride(name="Chiam See Tong", parliament_number=6, source_party="Singapore Democratic Alliance", party="Singapore Democratic Party", reason="test")]

    with pytest.raises(HansardWriteCheckError):
        get_party_changes([], overrides, [])


def test_party_override_for_a_row_holding_another_party_raises() -> None:
    speakers = [_get_speaker(1, "Chiam See Tong", 6, "Workers' Party")]
    overrides = [PartyOverride(name="Chiam See Tong", parliament_number=6, source_party="Singapore Democratic Alliance", party="Singapore Democratic Party", reason="test")]

    with pytest.raises(HansardWriteCheckError):
        get_party_changes(speakers, overrides, [])


def test_party_changes_refuse_a_colonial_member_without_a_stored_row() -> None:
    speakers = [_get_speaker(1, "David Marshall", 1, "Labour Front")]
    colonial_members = [HandKeptMember(name="David Marshall", party="Labour Front", is_legislative_assembly=True, parliament_number=0, comments=None)]

    with pytest.raises(HansardWriteCheckError):
        get_party_changes(speakers, [], colonial_members)
