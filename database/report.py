from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Optional

if TYPE_CHECKING:
    from database.speech import Speech

from pydantic import BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel
from sqlmodel import Field, Relationship, SQLModel

EmptyStrNoneInt = Annotated[
    Optional[int],
    BeforeValidator(lambda v: None if isinstance(v, str) and v.strip() == "" else v),
]


class Report(SQLModel, table=True):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    id: Optional[int] = Field(default=None, primary_key=True)

    volume_number: int = Field(alias="volumeNo")
    parliament_number: int = Field(alias="parlNo")
    sitting_number: EmptyStrNoneInt = Field(None, alias="sittingNo")
    sitting_date: datetime = Field(alias="sittingDate")
    speech_number: int = Field(alias="sno")

    original_title: str
    title: str
    subtitle: Optional[str] = None
    report_id: str = Field(alias="reportId")
    report_type: str = Field(alias="reportType")

    html_file_name: Optional[str] = Field(None, alias="htmlFileName")
    content: Optional[str] = None
    markdown_content: Optional[str] = None

    report_version: str = Field(alias="reportVersion")

    speeches: list["Speech"] = Relationship(back_populates="report")
