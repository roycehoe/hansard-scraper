from typing import Optional

from pydantic import BaseModel, ConfigDict


class ConstituencyName(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    printed: str
    constituency: str
    parliament_number: Optional[int] = None


class ConstituencyRowName(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sitting_date: str
    speaker_name: str
    printed: str
    constituency: str
    reason: str


class ConstituencyNames(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    names: list[ConstituencyName]
    rows: list[ConstituencyRowName]
