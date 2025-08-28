from datetime import datetime
from typing import Annotated, Optional

from pydantic import BeforeValidator
from sqlmodel import Field, SQLModel

EmptyStrNoneInt = Annotated[
    Optional[int],
    BeforeValidator(lambda v: None if isinstance(v, str) and v.strip() == "" else v),
]


class Report(SQLModel, table=True):
    __tablename__ = "test"

    id: int | None = Field(default=None, primary_key=True)

    volume_number: int = Field(alias="volumeNo")
    parliament_number: int = Field(alias="parlNo")
    sitting_number: EmptyStrNoneInt = Field(None, alias="sittingNo")
    sitting_date: datetime = Field(alias="sittingDate")
    speech_number: int = Field(alias="sno")

    title: str
    subtitle: Optional[str] = None
    # Can be used to obtain raw report via request params
    report_id: str = Field(alias="reportId")
    report_type: str = Field(alias="reportType")

    column_start: Optional[str] = Field(None, alias="columnStart")
    column_end: Optional[str] = Field(None, alias="columnEnd")
    html_file_name: Optional[str] = Field(None, alias="htmlFileName")
    content: Optional[str] = None
    markdown_content: Optional[str] = None

    report_version: str = Field(alias="reportVersion")
