from typing import Optional

from sqlmodel import Field, SQLModel


class Report(SQLModel, table=True):
    volume_no: str = Field(alias="volumeNo")
    report_type: str = Field(alias="reportType")
    report_version: str = Field(alias="reportVersion")
    sitting_no: Optional[str] = Field(None, alias="sittingNo")
    title: str
    column_start: Optional[str] = Field(None, alias="columnStart")
    parl_no: str = Field(alias="parlNo")
    column_end: Optional[str] = Field(None, alias="columnEnd")
    report_id: str = Field(alias="reportId")
    max_result: str = Field(alias="maxResult")
    sno: str
    from_month: str = Field(alias="fromMonth")
    from_day: str = Field(alias="fromDay")
    from_year: str = Field(alias="fromYear")
    subtitle: Optional[str] = None
    sitting_date: str = Field(alias="sittingDate")
    html_file_name: Optional[str] = Field(None, alias="htmlFileName")
