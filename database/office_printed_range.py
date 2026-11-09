from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

import database.attendance_office  # noqa: F401 registers AttendanceOffice so the foreign key resolves
import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves
from enums import OfficeClass


class OfficePrintedRange(SQLModel, table=True):
    __tablename__ = "office_printed_range"
    __table_args__ = (
        UniqueConstraint(
            "first_attendance_office_id",
            name="uq_office_printed_range_first_attendance_office_id",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    office_printed: str
    office_class: OfficeClass
    sitting_count: int
    first_sitting_date: datetime
    last_sitting_date: datetime

    built_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    speaker_id: int = Field(foreign_key="speaker.id", index=True)
    first_attendance_office_id: int = Field(foreign_key="attendance_office.id")
    last_attendance_office_id: int = Field(foreign_key="attendance_office.id")
