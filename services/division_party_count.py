from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from enums import DivisionVoteChoice, DivisionVoteListSource


@dataclass(frozen=True)
class DivisionVoteInput:
    vote_choice: DivisionVoteChoice
    party: Optional[str]
    is_party_uncertain: bool


@dataclass(frozen=True)
class PartyCount:
    list_source: DivisionVoteListSource
    vote_choice: DivisionVoteChoice
    party: Optional[str]
    member_count: int
    uncertain_member_count: int


def _count_party_votes(
    list_source: DivisionVoteListSource, votes: list[DivisionVoteInput]
) -> list[PartyCount]:
    choice_and_party_to_votes: defaultdict[
        tuple[DivisionVoteChoice, Optional[str]], list[DivisionVoteInput]
    ] = defaultdict(list)
    for vote in votes:
        if (
            vote.vote_choice != DivisionVoteChoice.AYE
            and vote.vote_choice != DivisionVoteChoice.NO
            and vote.vote_choice != DivisionVoteChoice.ABSTAIN
        ):
            continue
        choice_and_party_to_votes[(vote.vote_choice, vote.party)].append(vote)
    vote_choices = list(DivisionVoteChoice)
    return [
        PartyCount(
            list_source=list_source,
            vote_choice=vote_choice,
            party=party,
            member_count=len(choice_and_party_to_votes[(vote_choice, party)]),
            uncertain_member_count=sum(
                vote.is_party_uncertain
                for vote in choice_and_party_to_votes[(vote_choice, party)]
            ),
        )
        for vote_choice, party in sorted(
            choice_and_party_to_votes,
            key=lambda choice_and_party: (
                vote_choices.index(choice_and_party[0]),
                choice_and_party[1] is None,
                choice_and_party[1] or "",
            ),
        )
    ]


def get_division_party_counts(
    minutes_votes: list[DivisionVoteInput],
    hansard_votes: list[DivisionVoteInput],
    is_minutes_list_stored: bool,
    is_hansard_list_stored: bool,
) -> list[PartyCount]:
    if is_minutes_list_stored:
        return _count_party_votes(DivisionVoteListSource.MINUTES, minutes_votes)
    if is_hansard_list_stored:
        return _count_party_votes(DivisionVoteListSource.HANSARD, hansard_votes)
    return []
