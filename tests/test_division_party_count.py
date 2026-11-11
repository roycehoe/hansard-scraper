from typing import Optional

from enums import DivisionVoteChoice, DivisionVoteListSource
from services.division_party_count import (
    DivisionVoteInput,
    PartyCount,
    get_division_party_counts,
)

_PARTY = "PAP"
_OTHER_PARTY = "WP"
_MEMBER_COUNT = 3
_UNCERTAIN_MEMBER_COUNT = 2


def _build_vote(
    vote_choice: DivisionVoteChoice,
    party: Optional[str],
    is_party_uncertain: bool = False,
) -> DivisionVoteInput:
    return DivisionVoteInput(
        vote_choice=vote_choice, party=party, is_party_uncertain=is_party_uncertain
    )


def test_minutes_list_is_counted_when_stored() -> None:
    minutes_votes = [_build_vote(DivisionVoteChoice.AYE, _PARTY)]
    hansard_votes = [
        _build_vote(DivisionVoteChoice.AYE, _PARTY),
        _build_vote(DivisionVoteChoice.AYE, _PARTY),
    ]

    party_counts = get_division_party_counts(
        minutes_votes, hansard_votes, True, True
    )

    assert party_counts == [
        PartyCount(
            DivisionVoteListSource.MINUTES, DivisionVoteChoice.AYE, _PARTY, 1, 0
        )
    ]


def test_hansard_list_is_counted_when_the_minutes_list_is_not_stored() -> None:
    hansard_votes = [
        _build_vote(DivisionVoteChoice.NO, _OTHER_PARTY),
        _build_vote(DivisionVoteChoice.NO, _OTHER_PARTY),
    ]

    party_counts = get_division_party_counts([], hansard_votes, False, True)

    assert party_counts == [
        PartyCount(
            DivisionVoteListSource.HANSARD, DivisionVoteChoice.NO, _OTHER_PARTY, 2, 0
        )
    ]


def test_nothing_is_counted_when_neither_list_is_stored() -> None:
    votes = [_build_vote(DivisionVoteChoice.AYE, _PARTY)]

    assert get_division_party_counts(votes, votes, False, False) == []


def test_absent_and_paired_rows_are_left_out() -> None:
    minutes_votes = [
        _build_vote(DivisionVoteChoice.AYE, _PARTY),
        _build_vote(DivisionVoteChoice.ABSTAIN, _PARTY),
        _build_vote(DivisionVoteChoice.ABSENT, _PARTY),
        _build_vote(DivisionVoteChoice.PAIRED, _PARTY),
    ]

    party_counts = get_division_party_counts(minutes_votes, [], True, False)

    assert [party_count.vote_choice for party_count in party_counts] == [
        DivisionVoteChoice.AYE,
        DivisionVoteChoice.ABSTAIN,
    ]


def test_an_unlinked_name_counts_under_a_null_party() -> None:
    minutes_votes = [
        _build_vote(DivisionVoteChoice.AYE, None),
        _build_vote(DivisionVoteChoice.AYE, None),
        _build_vote(DivisionVoteChoice.AYE, _PARTY),
    ]

    party_counts = get_division_party_counts(minutes_votes, [], True, False)

    assert [(party_count.party, party_count.member_count) for party_count in party_counts] == [
        (_PARTY, 1),
        (None, 2),
    ]


def test_uncertain_members_are_counted_in_both_columns() -> None:
    minutes_votes = [
        _build_vote(DivisionVoteChoice.NO, _PARTY, is_party_uncertain=True),
        _build_vote(DivisionVoteChoice.NO, _PARTY),
        _build_vote(DivisionVoteChoice.NO, _PARTY, is_party_uncertain=True),
    ]

    (party_count,) = get_division_party_counts(minutes_votes, [], True, False)

    assert party_count.member_count == _MEMBER_COUNT
    assert party_count.uncertain_member_count == _UNCERTAIN_MEMBER_COUNT
