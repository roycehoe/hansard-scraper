from dataclasses import dataclass

from enums import DivisionVoteChoice


@dataclass(frozen=True)
class ParsedVoteName:
    ordinal: int
    printed_name: str
    vote_choice: DivisionVoteChoice
