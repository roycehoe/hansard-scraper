from datetime import datetime

import pytest

import database.speech  # noqa: F401 registers Speech so the Report relationship resolves
from crud.speech import SpeechSpeakerRow
from database.speaker import Speaker
from exceptions import HansardWriteCheckError
from schemas.hand_kept_member import HandKeptMember
from schemas.head_of_state import HeadOfStateResult
from services.attendance import build_speaker_lookups
from services.speaker import ParliamentChange, get_parliament_changes
from services.speaker_link import resolve_speech_rows
from utils.data_files import (
    get_colonial_members,
    get_heads_of_state,
    get_person_decisions,
)
from utils.parliament_numbers import VOLUME_TO_PARLIAMENT, infer_parliament
from utils.speaker_resolution import NAME_PARLIAMENT_TO_CANONICAL_SPEAKER
from utils.speaker_resolution_constants import COLONIAL_PARLIAMENT_NUMBER

_ASSEMBLY_ONLY_ROW_COUNT = 71
_DUAL_COLONIAL_NAMES = frozenset({"Devan Nair, Mrs", "Lim Huan Boon"})
_REKEYED_NAME_COUNT = 12
_LAST_ASSEMBLY_VOLUME = 23


def _get_speaker(speaker_id: int, name: str, parliament_number: int) -> Speaker:
    return Speaker(id=speaker_id, name=name, party="Labour Front", is_legislative_assembly=True, parliament_number=parliament_number)


def _get_member(name: str, parliament_number: int) -> HandKeptMember:
    return HandKeptMember(name=name, party="Labour Front", is_legislative_assembly=True, parliament_number=parliament_number, comments=None)


def test_a_row_the_file_puts_in_parliament_zero_moves_from_parliament_one() -> None:
    speakers = [_get_speaker(1, "David Marshall", 1), _get_speaker(2, "Devan Nair, Mrs", 1)]
    colonial_members = [_get_member("David Marshall", 0), _get_member("Devan Nair, Mrs", 1)]

    assert get_parliament_changes(speakers, colonial_members, []) == [ParliamentChange(1, "David Marshall", 1, 0)]


def test_a_head_of_state_the_file_puts_in_parliament_zero_moves_too() -> None:
    speakers = [_get_speaker(1, "John Nicoll", 1), _get_speaker(2, "Yusof bin Ishak", 1)]
    heads_of_state = [
        HeadOfStateResult(name="John Nicoll", parliament_number=0, comments="Governor"),
        HeadOfStateResult(name="Yusof bin Ishak", parliament_number=1, comments="Yang di-Pertuan Negara"),
    ]

    assert get_parliament_changes(speakers, [], heads_of_state) == [ParliamentChange(1, "John Nicoll", 1, 0)]


def test_parliament_changes_are_empty_once_applied() -> None:
    speakers = [_get_speaker(1, "David Marshall", 0)]

    assert get_parliament_changes(speakers, [_get_member("David Marshall", 0)], []) == []


def test_a_row_in_neither_parliament_raises() -> None:
    with pytest.raises(HansardWriteCheckError):
        get_parliament_changes([], [_get_member("David Marshall", 0)], [])


def test_rows_in_both_parliaments_raise() -> None:
    speakers = [_get_speaker(1, "David Marshall", 1), _get_speaker(2, "David Marshall", 0)]

    with pytest.raises(HansardWriteCheckError):
        get_parliament_changes(speakers, [_get_member("David Marshall", 0)], [])


def test_data_files_put_71_assembly_only_rows_in_parliament_zero_and_the_two_dual_members_in_parliament_one() -> None:
    colonial_members = get_colonial_members()
    heads_of_state = get_heads_of_state()

    zero_names = [member.name for member in colonial_members if member.parliament_number == COLONIAL_PARLIAMENT_NUMBER]
    zero_names += [head.name for head in heads_of_state if head.parliament_number == COLONIAL_PARLIAMENT_NUMBER]
    assert len(zero_names) == _ASSEMBLY_ONLY_ROW_COUNT
    assert len(set(zero_names)) == _ASSEMBLY_ONLY_ROW_COUNT
    assert {member.name for member in colonial_members if member.parliament_number == 1} == _DUAL_COLONIAL_NAMES
    assert {head.name for head in heads_of_state if head.parliament_number == COLONIAL_PARLIAMENT_NUMBER} == {"John Nicoll", "Robert Black", "William Goode"}


def test_person_decisions_key_a_moved_row_to_parliament_zero() -> None:
    zero_names = {member.name for member in get_colonial_members() if member.parliament_number == COLONIAL_PARLIAMENT_NUMBER}
    zero_names |= {head.name for head in get_heads_of_state() if head.parliament_number == COLONIAL_PARLIAMENT_NUMBER}
    decisions = get_person_decisions()

    members = [member for decision in decisions for member in decision.members if member.name in zero_names]
    assert members
    assert all(member.parliament_number == COLONIAL_PARLIAMENT_NUMBER for member in members)


def test_name_map_keys_a_moved_member_to_parliament_zero_and_a_dual_member_to_parliament_one() -> None:
    zero_names = {member.name for member in get_colonial_members() if member.parliament_number == COLONIAL_PARLIAMENT_NUMBER}
    zero_names |= {head.name for head in get_heads_of_state() if head.parliament_number == COLONIAL_PARLIAMENT_NUMBER}

    moved_keys = [key for key, canonical in NAME_PARLIAMENT_TO_CANONICAL_SPEAKER.items() if canonical in zero_names]
    assert len(moved_keys) == _REKEYED_NAME_COUNT
    assert all(parliament == COLONIAL_PARLIAMENT_NUMBER for _, parliament in moved_keys)
    assert NAME_PARLIAMENT_TO_CANONICAL_SPEAKER[("c v devan nair", 1)] == "Devan Nair, Mrs"


def test_volumes_of_1955_to_1959_are_parliament_zero() -> None:
    assert infer_parliament(None, 1) == COLONIAL_PARLIAMENT_NUMBER
    assert infer_parliament(None, 11) == COLONIAL_PARLIAMENT_NUMBER
    assert infer_parliament(None, 12) == COLONIAL_PARLIAMENT_NUMBER
    assert infer_parliament(None, 24) == 1
    assert all(parliament == COLONIAL_PARLIAMENT_NUMBER for volume, parliament in VOLUME_TO_PARLIAMENT.items() if volume <= _LAST_ASSEMBLY_VOLUME)


def test_the_chief_minister_of_7_june_1956_is_david_marshall() -> None:
    speakers = [_get_speaker(1, "David Marshall", 0), _get_speaker(2, "Lim Yew Hock", 0)]
    lookups = build_speaker_lookups(speakers)
    name_parliament_number_to_speaker_id = {(speaker.name, speaker.parliament_number): speaker.id for speaker in speakers}
    speech_speaker_rows = [
        SpeechSpeakerRow(10, "The Chief Minister", 0, datetime(1956, 6, 6)),
        SpeechSpeakerRow(11, "The Chief Minister", 0, datetime(1956, 6, 7)),
        SpeechSpeakerRow(12, "The Chief Minister", 0, datetime(1956, 6, 8)),
        SpeechSpeakerRow(13, "The Chief Minister", 0, datetime(1956, 8, 29)),
    ]

    assert resolve_speech_rows(speech_speaker_rows, lookups, name_parliament_number_to_speaker_id).id_to_speaker_id == {10: 1, 11: 1, 12: 2, 13: 2}
