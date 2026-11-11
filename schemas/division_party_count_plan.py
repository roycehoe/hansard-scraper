from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import DivisionVoteChoice, DivisionVoteListSource


class PlannedDivisionPartyCount(BaseModel):
    model_config = ConfigDict(frozen=True)

    division_id: int
    list_source: DivisionVoteListSource
    vote_choice: DivisionVoteChoice
    party: Optional[str]
    member_count: int
    uncertain_member_count: int


class DivisionPartyCountPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    division_ids: list[int]
    party_counts: list[PlannedDivisionPartyCount]
