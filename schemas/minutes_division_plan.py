from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import (
    DivisionListStatus,
    DivisionVoteChoice,
    DivisionVoteNameRule,
    MinutesDivisionPairing,
)


class PlannedDivisionVote(BaseModel):
    model_config = ConfigDict(frozen=True)

    ordinal: int
    printed_name: str
    vote_choice: DivisionVoteChoice
    speaker_id: Optional[int]
    name_rule: Optional[DivisionVoteNameRule]
    party: Optional[str]
    is_party_uncertain: bool


class PlannedMinutesOnlyDivision(BaseModel):
    model_config = ConfigDict(frozen=True)

    sitting_date: date
    parliament_number: int
    printed_counts: str
    ayes: int
    noes: int
    abstentions: Optional[int]


class PlannedMinutesDivision(BaseModel):
    model_config = ConfigDict(frozen=True)

    minutes_id: int
    sitting_date: date
    ordinal: int
    printed_counts: str
    ayes: int
    noes: int
    abstentions: Optional[int]
    list_status: DivisionListStatus
    printed_list: Optional[str]
    pairing: MinutesDivisionPairing
    division_id: Optional[int]
    new_division: Optional[PlannedMinutesOnlyDivision]
    votes: list[PlannedDivisionVote]


class PlannedMinutesReview(BaseModel):
    model_config = ConfigDict(frozen=True)

    minutes_id: int
    status_note: str


class MinutesDivisionPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    minutes_ids: list[int]
    minutes_to_review: list[PlannedMinutesReview]
    minutes_divisions: list[PlannedMinutesDivision]
