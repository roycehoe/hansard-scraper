from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, RootModel, model_validator

from enums import PersonDecisionKind

_MIN_LINKED_MEMBER_COUNT = 2


class PersonDecisionMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    parliament_number: int


class PersonDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    person_name: Optional[str]
    members: list[PersonDecisionMember] = Field(min_length=1)
    decision: PersonDecisionKind
    source: str

    @model_validator(mode="after")
    def _validate_members_and_name(self) -> "PersonDecision":
        if self.decision == PersonDecisionKind.NAME and len(self.members) != 1:
            raise ValueError("a name decision has exactly one member")
        if self.decision == PersonDecisionKind.NAME and not self.person_name:
            raise ValueError("a name decision needs a person_name")
        if self.decision == PersonDecisionKind.DISTINCT and len(self.members) < _MIN_LINKED_MEMBER_COUNT:
            raise ValueError("a distinct decision needs at least two members")
        if self.decision == PersonDecisionKind.MERGE and len(self.members) < _MIN_LINKED_MEMBER_COUNT:
            raise ValueError("a merge decision needs at least two members")
        return self


class PersonDecisions(RootModel[list[PersonDecision]]):
    model_config = ConfigDict(frozen=True)
