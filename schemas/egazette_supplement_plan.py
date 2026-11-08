from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from enums import EgazetteSupplementKind


class PlannedEgazetteSupplement(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    year: int
    supplement_kind: EgazetteSupplementKind
    number: int
    file_path: str
    size_bytes: int
    sha256: str
    printed_title: str
    printed_bill_number: str
    bill_number: str
    first_reading_date: date
    passing_date: Optional[date]
    printed_act_number: Optional[str]
    fetched_at: datetime


class UnparsedEgazetteSupplement(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    message: str


class EgazetteSupplementPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    supplements: list[PlannedEgazetteSupplement]
    unparsed: list[UnparsedEgazetteSupplement]
    missing_count: int
