from datetime import date

from pydantic import BaseModel, ConfigDict, RootModel


class LeaveHeadingYear(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sitting_date: date
    printed_heading: str
    year: int
    reason: str


class LeaveHeadingYears(RootModel[list[LeaveHeadingYear]]):
    model_config = ConfigDict(frozen=True)
