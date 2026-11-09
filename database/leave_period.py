from datetime import date
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.sitting  # noqa: F401 registers Sitting so the foreign key resolves
import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves
from enums import (
    LeaveEntryFormat,
    LeaveNameSource,
    LeaveOfficeSource,
    LeaveSpeakerLinkSource,
    LeaveYearSource,
)


class LeavePeriod(SQLModel, table=True):
    __tablename__ = "leave_period"
    __table_args__ = (
        UniqueConstraint("period_key", name="uq_leave_period_period_key"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    period_key: str
    name: Optional[str] = None
    start_date: Optional[date] = Field(default=None, index=True)
    end_date: Optional[date] = None
    end_text: Optional[str] = None


class LeavePeriodPrinting(SQLModel, table=True):
    __tablename__ = "leave_period_printing"
    __table_args__ = (
        UniqueConstraint(
            "sitting_id", "ordinal", name="uq_leave_period_printing_sitting_id_ordinal"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    sitting_date: date = Field(index=True)
    printed_name: Optional[str] = None
    carried_name: Optional[str] = None
    printed_from: Optional[str] = None
    printed_to: Optional[str] = None
    printed_line: Optional[str] = None
    printed_heading_from: Optional[str] = None
    printed_heading_to: Optional[str] = None
    office_printed: Optional[str] = None
    entry_format: LeaveEntryFormat
    name_source: LeaveNameSource
    year_source: Optional[LeaveYearSource] = None
    speaker_link_source: Optional[LeaveSpeakerLinkSource] = None
    office_source: Optional[LeaveOfficeSource] = None

    is_covering_sitting: Optional[bool] = None

    sitting_id: int = Field(foreign_key="sitting.id", index=True)
    leave_period_id: int = Field(foreign_key="leave_period.id", index=True)
    speaker_id: Optional[int] = Field(
        default=None, foreign_key="speaker.id", index=True
    )
