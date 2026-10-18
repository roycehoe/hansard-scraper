from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from enums import DatePrecision


class PartyAffiliationSpan(BaseModel):
    party: str
    # NOTE: precision is declared before started_on so the date validator can read it from info.data
    started_on_precision: DatePrecision
    started_on: date
    event: str
    is_started_on_upper_bound: bool
    source_url: Optional[str] = None
    source_report_id: Optional[int] = None

    @field_validator("started_on", mode="before")
    @classmethod
    def _expand_month_date(cls, started_on: object, info: ValidationInfo) -> object:
        if info.data.get("started_on_precision") == DatePrecision.MONTH:
            return f"{started_on}-01"
        return started_on


class MembershipPartyAffiliations(BaseModel):
    name: str
    parliament_number: int
    affiliations: list[PartyAffiliationSpan] = Field(min_length=1)
