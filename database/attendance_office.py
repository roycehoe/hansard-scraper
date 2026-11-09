from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

import database.attendance  # noqa: F401 registers Attendance so the foreign key resolves
from enums import AttendanceOfficeSource, OfficeClass


class AttendanceOffice(SQLModel, table=True):
    __tablename__ = "attendance_office"
    __table_args__ = (
        UniqueConstraint("attendance_id", name="uq_attendance_office_attendance_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    office_printed: str
    entry_line_printed: str
    office_class: OfficeClass
    source: AttendanceOfficeSource

    extracted_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )

    attendance_id: int = Field(foreign_key="attendance.id")
