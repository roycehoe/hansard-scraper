from typing import Optional

from pydantic import BaseModel, ConfigDict, RootModel


class HandKeptMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    party: str
    is_legislative_assembly: bool
    parliament_number: int
    comments: Optional[str]


class HandKeptMembers(RootModel[list[HandKeptMember]]):
    model_config = ConfigDict(frozen=True)
