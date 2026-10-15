from typing import Optional

from sqlalchemy import Index, text
from sqlmodel import Field, Relationship, SQLModel

from database.report import Report
from enums import SpeechKind


class Speech(SQLModel, table=True):
    __table_args__ = (
        Index("ix_speech_transcript_fts", text("to_tsvector('english', transcript)"), postgresql_using="gin"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    speaker: Optional[str]
    transcript: str
    kind: Optional[SpeechKind] = None

    report_id: Optional[int] = Field(default=None, foreign_key="report.id", index=True)
    report: Report = Relationship(back_populates="speeches")
    speaker_id: Optional[int] = Field(default=None, foreign_key="speaker.id", index=True)
