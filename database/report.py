from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Optional

if TYPE_CHECKING:
    from database.speech import Speech

from pydantic import BeforeValidator, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import Column, Computed, Index, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlmodel import Field, Relationship, SQLModel

EmptyStrNoneInt = Annotated[
    Optional[int],
    BeforeValidator(lambda value: None if isinstance(value, str) and value.strip() == "" else value),
]


class Report(SQLModel, table=True):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    __table_args__ = (
        # NOTE: a second index on the primary key, so the person page reads parliament_number without the heap
        Index("ix_report_id_parliament_number", "id", postgresql_include=["parliament_number"]),
        Index("ix_report_sitting_date_parliament_number", "sitting_date", "parliament_number"),
        Index("ix_report_title_fts", text("to_tsvector('english', title)"), postgresql_using="gin"),
        Index("ix_report_title_tsv", "title_tsv", postgresql_using="gin"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    volume_number: int = Field(alias="volumeNo")
    parliament_number: int = Field(alias="parlNo")
    sitting_number: EmptyStrNoneInt = Field(None, alias="sittingNo")
    sitting_date: datetime = Field(alias="sittingDate")
    speech_number: int = Field(alias="sno")

    original_title: str
    title: str
    subtitle: Optional[str] = None
    title_tsv: Optional[str] = Field(
        default=None,
        sa_column=Column(TSVECTOR, Computed("to_tsvector('english'::regconfig, title)", persisted=True)),
    )
    report_id: str = Field(alias="reportId", unique=True)
    report_type: str = Field(alias="reportType")

    html_file_name: Optional[str] = Field(None, alias="htmlFileName")
    content: Optional[str] = None
    markdown_content: Optional[str] = None

    report_version: str = Field(alias="reportVersion")

    speeches: list["Speech"] = Relationship(back_populates="report")
