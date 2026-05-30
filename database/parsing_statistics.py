from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from database.report import EmptyStrNoneInt


class ParsingStatistics(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    volume_number: int = Field(alias="volumeNo")
    parliament_number: int = Field(alias="parlNo")
    sitting_number: EmptyStrNoneInt = Field(None, alias="sittingNo")
    sitting_date: datetime = Field(alias="sittingDate")
    speech_number: int = Field(alias="sno")

    title: str
    subtitle: Optional[str] = None
    has_markdown: bool
    has_start_line: bool
    can_get_speeches: bool
    report_type: str = Field(alias="reportType")

    report_version: str = Field(alias="reportVersion")
