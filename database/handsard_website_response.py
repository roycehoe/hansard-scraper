from typing import Optional

from sqlmodel import Field, SQLModel


class HandsardWebsiteResponse(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    volume_number: str = Field(alias="volumeNo")
    parliament_number: str = Field(alias="parlNo")
    sitting_number: Optional[str] = Field(None, alias="sittingNo")
    sitting_date: str = Field(alias="sittingDate")
    speech_number: str = Field(alias="sno")

    title: str
    subtitle: Optional[str] = None
    report_id: str = Field(alias="reportId")
    report_type: str = Field(alias="reportType")

    html_file_name: Optional[str] = Field(None, alias="htmlFileName")
    content: Optional[str] = None

    report_version: str = Field(alias="reportVersion")
