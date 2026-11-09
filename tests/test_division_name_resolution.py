from typing import Optional

from database.speaker import Speaker
from enums import DivisionVoteNameRule
from services.attendance import (
    build_inverted_name_to_canonical,
    build_speaker_lookups,
)
from services.speaker_link import VoteSpeakerMatch, resolve_vote_speaker
from utils.speaker_resolution import resolve_canonical_name

_PARLIAMENT_NUMBER = 14
_COLONIAL_PARLIAMENT_NUMBER = 0
_PARTY = "People's Action Party"
_HAND_LIST_PRINTED_NAME = "Masagos Zulkifli B M M"
_HAND_LIST_CANONICAL_NAME = "Masagos Zulkifli Bin Masagos Mohamad"


def _build_speaker(speaker_id: int, name: str, parliament_number: int) -> Speaker:
    return Speaker(
        id=speaker_id,
        name=name,
        party=_PARTY,
        is_legislative_assembly=False,
        parliament_number=parliament_number,
    )


def _resolve(
    name: str, parliament_number: int, speakers: list[Speaker]
) -> Optional[VoteSpeakerMatch]:
    return resolve_vote_speaker(
        name,
        parliament_number,
        build_speaker_lookups(speakers),
        build_inverted_name_to_canonical(speakers),
        {
            (speaker.name, speaker.parliament_number): speaker.id
            for speaker in speakers
            if speaker.id is not None
        },
    )


def test_exact_name_links_with_rule_exact() -> None:
    speakers = [_build_speaker(1, "Eugene Tan Kheng Boon", _PARLIAMENT_NUMBER)]

    assert _resolve("Eugene Tan Kheng Boon", _PARLIAMENT_NUMBER, speakers) == (
        VoteSpeakerMatch(1, DivisionVoteNameRule.EXACT)
    )


def test_printed_surname_first_form_links_with_rule_inverted() -> None:
    speakers = [_build_speaker(1, "Louis Chua Kheng Wee", _PARLIAMENT_NUMBER)]

    assert _resolve("Chua Kheng Wee, Louis", _PARLIAMENT_NUMBER, speakers) == (
        VoteSpeakerMatch(1, DivisionVoteNameRule.INVERTED)
    )


def test_bin_free_form_links_with_rule_bin_free() -> None:
    speakers = [_build_speaker(1, "Abdul Samad Bin Abdullah", _PARLIAMENT_NUMBER)]

    assert _resolve("Abdul Samad Abdullah", _PARLIAMENT_NUMBER, speakers) == (
        VoteSpeakerMatch(1, DivisionVoteNameRule.BIN_FREE)
    )


def test_same_words_in_another_order_links_with_rule_same_words() -> None:
    speakers = [_build_speaker(1, "Tan Wei Ming", _PARLIAMENT_NUMBER)]

    assert _resolve("Ming Tan Wei", _PARLIAMENT_NUMBER, speakers) == (
        VoteSpeakerMatch(1, DivisionVoteNameRule.SAME_WORDS)
    )


def test_hand_list_misprint_links_with_rule_hand_list() -> None:
    speakers = [
        _build_speaker(1, _HAND_LIST_CANONICAL_NAME, _PARLIAMENT_NUMBER),
    ]

    assert _resolve(_HAND_LIST_PRINTED_NAME, _PARLIAMENT_NUMBER, speakers) == (
        VoteSpeakerMatch(1, DivisionVoteNameRule.HAND_LIST)
    )


def test_subset_name_does_not_link() -> None:
    speakers = [_build_speaker(1, "Eugene Tan K Boon", _PARLIAMENT_NUMBER)]

    assert _resolve("Eugene Tan Boon", _PARLIAMENT_NUMBER, speakers) is None


def test_prefix_name_does_not_link() -> None:
    speakers = [_build_speaker(1, "Eugene Tan Kheng Boon", _PARLIAMENT_NUMBER)]

    assert _resolve("Eugene Tan", _PARLIAMENT_NUMBER, speakers) is None


def test_surname_only_name_does_not_link() -> None:
    speakers = [_build_speaker(1, "Louis Chua Kheng Wee", _PARLIAMENT_NUMBER)]

    assert _resolve("Wee", _PARLIAMENT_NUMBER, speakers) is None


def test_name_two_members_fit_does_not_link() -> None:
    same_name_speakers = [
        _build_speaker(1, "Tan Wei Ming", _PARLIAMENT_NUMBER),
        _build_speaker(2, "Tan Wei Ming", _PARLIAMENT_NUMBER),
    ]
    tier_conflict_speakers = [
        _build_speaker(1, "Tan Wei Ming", _PARLIAMENT_NUMBER),
        _build_speaker(2, "Ming Wei Tan", _PARLIAMENT_NUMBER),
    ]

    assert _resolve("Tan Wei Ming", _PARLIAMENT_NUMBER, same_name_speakers) is None
    assert _resolve("Tan Wei Ming", _PARLIAMENT_NUMBER, tier_conflict_speakers) is None


def test_colonial_name_matching_one_membership_links() -> None:
    speakers = [_build_speaker(1, "Lim Yew Hock", 1)]

    assert _resolve("Lim Yew Hock", _COLONIAL_PARLIAMENT_NUMBER, speakers) == (
        VoteSpeakerMatch(1, DivisionVoteNameRule.EXACT)
    )


def test_colonial_name_matching_two_parliaments_does_not_link() -> None:
    speakers = [
        _build_speaker(1, "Lim Yew Hock", 1),
        _build_speaker(2, "Lim Yew Hock", 2),
    ]

    assert _resolve("Lim Yew Hock", _COLONIAL_PARLIAMENT_NUMBER, speakers) is None


def test_resolve_canonical_name_still_links_a_subset_name() -> None:
    speakers = [_build_speaker(1, "Eugene Tan K Boon", _PARLIAMENT_NUMBER)]

    assert (
        resolve_canonical_name(
            "Eugene Tan Boon", _PARLIAMENT_NUMBER, build_speaker_lookups(speakers)
        )
        == "Eugene Tan K Boon"
    )
