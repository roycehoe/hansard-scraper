from datetime import date

from pydantic import BaseModel, ConfigDict, RootModel


class LeaveLineReading(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sitting_date: date
    printed_line: str
    readings: list[str]
    reason: str


class LeaveLineReadings(RootModel[list[LeaveLineReading]]):
    model_config = ConfigDict(frozen=True)
