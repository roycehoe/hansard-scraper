from datetime import date
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class ActsSupplementCapture(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    original_url: str
    archive_timestamp: str
    capture_url: str = Field(unique=True)
    content: str


class ActsSupplementEntry(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "act_number", "link", name="uq_actssupplemententry_act_number_link"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    printed_title: str
    printed_number: str
    link: str
    pdf_link: Optional[str] = None
    pdf_size: Optional[str] = None
    act_number: str
    publication_date: date

    capture_id: int = Field(foreign_key="actssupplementcapture.id", index=True)
