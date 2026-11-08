from datetime import date
from typing import Optional

from sqlmodel import Field, SQLModel


class RepealedActsCapture(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    original_url: str
    archive_timestamp: str
    capture_url: str = Field(unique=True)
    content: str


class RepealedActEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    printed_title: str
    printed_chapter: Optional[str] = None
    link: str
    sso_code: str = Field(unique=True)
    enactment_year: Optional[int] = None
    repeal_date: date
    last_version_date: date

    capture_id: int = Field(foreign_key="repealedactscapture.id", index=True)
