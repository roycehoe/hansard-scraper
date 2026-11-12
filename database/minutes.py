from datetime import date, datetime
from typing import Optional

from sqlalchemy import Column, DateTime, LargeBinary
from sqlmodel import Field, SQLModel

from enums import MinutesFileFormat, MinutesIndexSource, MinutesStatus


class MinutesIndexCapture(SQLModel, table=True):
    __tablename__ = "minutes_index_capture"

    id: Optional[int] = Field(default=None, primary_key=True)

    original_url: str
    archive_timestamp: Optional[str] = None
    capture_url: str = Field(unique=True)
    content: str


class Minutes(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    sitting_date: date = Field(unique=True)
    printed_label: Optional[str] = None
    printed_parliament: Optional[str] = None
    file_url: Optional[str] = None
    archive_timestamp: Optional[str] = None
    file_format: Optional[MinutesFileFormat] = None
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    file_bytes: Optional[bytes] = Field(
        default=None, sa_column=Column(LargeBinary, nullable=True)
    )
    extracted_text: Optional[str] = None
    status_note: Optional[str] = None

    fetched_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    status: MinutesStatus
    index_source: Optional[MinutesIndexSource] = None

    index_capture_id: Optional[int] = Field(
        default=None, foreign_key="minutes_index_capture.id", index=True
    )
