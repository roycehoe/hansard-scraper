from typing import Optional

from pydantic import BaseModel


class ConstituencyName(BaseModel):
    printed: str
    constituency: str
    parliament_number: Optional[int] = None


class ConstituencyRowName(BaseModel):
    sitting_date: str
    speaker_name: str
    printed: str
    constituency: str
    reason: str


class ConstituencyNames(BaseModel):
    names: list[ConstituencyName]
    rows: list[ConstituencyRowName]
