from typing import Optional

from sqlmodel import Field, SQLModel


class SittingAttendance(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    sitting_id: int | None = Field(default=None, foreign_key="handsardsittingdateresponse.id")

    mp_name: Optional[str] = None
    attendance: Optional[bool] = None
    location_name: Optional[str] = None
