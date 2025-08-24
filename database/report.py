from typing import Optional

from sqlmodel import Field, SQLModel


class Report(SQLModel, table=True):
    volume_number: str = Field(alias="volumeNo")
    parliament_number: str = Field(alias="parlNo")
    sitting_number: Optional[str] = Field(None, alias="sittingNo")
    sitting_date: str = Field(alias="sittingDate")
    speech_number: str

    title: str
    subtitle: Optional[str] = None
    # Can be used to obtain raw report via request params
    report_id: str = Field(alias="reportId")
    report_type: str = Field(alias="reportType")

    column_start: Optional[str] = Field(None, alias="columnStart")
    column_end: Optional[str] = Field(None, alias="columnEnd")
    html_file_name: Optional[str] = Field(None, alias="htmlFileName")

    report_version: str = Field(alias="reportVersion")
