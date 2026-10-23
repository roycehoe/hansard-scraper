from datetime import date
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    ValidationInfo,
    field_validator,
    model_validator,
)

from enums import DatePrecision


class PartyAffiliationSpan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

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

    @model_validator(mode="after")
    def _validate_exactly_one_source(self) -> "PartyAffiliationSpan":
        if self.source_url is None and self.source_report_id is None:
            raise ValueError("a span needs source_url or source_report_id")
        if self.source_url is not None and self.source_report_id is not None:
            raise ValueError("a span takes only one of source_url and source_report_id")
        return self


class MembershipPartyAffiliations(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    parliament_number: int
    affiliations: list[PartyAffiliationSpan] = Field(min_length=1)


class PartyAffiliationMemberships(RootModel[list[MembershipPartyAffiliations]]):
    model_config = ConfigDict(frozen=True)
