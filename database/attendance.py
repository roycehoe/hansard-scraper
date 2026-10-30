from typing import Optional

from pydantic import ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


class Attendance(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("sitting_id", "speaker_id", name="uq_attendance_sitting_id_speaker_id"),
        Index("ix_attendance_speaker_id", "speaker_id", postgresql_include=["is_present", "sitting_id", "location_name"]),
        Index("ix_attendance_location_name_speaker_id", "location_name", "speaker_id"),
    )

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: Optional[int] = Field(default=None, primary_key=True)
    sitting_id: int = Field(foreign_key="sitting.id", index=True)

    speaker_name: Optional[str] = None
    is_present: Optional[bool] = Field(default=None, alias="attendance")
    location_name: Optional[str] = None
    speaker_id: Optional[int] = Field(default=None, foreign_key="speaker.id")
