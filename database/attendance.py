from typing import Optional

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from sqlmodel import Field, SQLModel


class Attendance(SQLModel, table=True):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: Optional[int] = Field(default=None, primary_key=True)
    sitting_id: Optional[int] = Field(default=None, foreign_key="sitting.id")

    mp_name: Optional[str] = None
    attendance: Optional[bool] = None
    location_name: Optional[str] = None
    speaker_id: Optional[int] = Field(default=None, foreign_key="speaker.id")
