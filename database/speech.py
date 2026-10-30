from datetime import datetime
from typing import Optional

from sqlalchemy import Column, Computed, Index, text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlmodel import Field, Relationship, SQLModel

from database.report import Report
from enums import ColumnNote, SpeechKind


class Speech(SQLModel, table=True):
    __table_args__ = (
        Index("ix_speech_speaker_id", "speaker_id", "sitting_date", "id", postgresql_include=["report_id", "speaker"]),
        Index("ix_speech_transcript_fts", text("to_tsvector('english', transcript)"), postgresql_using="gin"),
        Index("ix_speech_transcript_tsv", "transcript_tsv", postgresql_using="gin"),
        Index(
            "ix_speech_transcript_tsv_rum",
            "transcript_tsv",
            "report_type",
            postgresql_using="rum",
            postgresql_ops={"transcript_tsv": "rum_tsvector_ops", "report_type": "rum_varchar_ops"},
        ),
        Index(
            "ix_speech_transcript_tsv_sitting_date_rum",
            "transcript_tsv",
            "report_type",
            "sitting_date",
            postgresql_using="rum",
            postgresql_ops={"transcript_tsv": "rum_tsvector_addon_ops", "report_type": "rum_varchar_ops"},
            postgresql_with={"attach": "sitting_date", "to": "transcript_tsv"},
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    speaker: Optional[str]
    transcript: str
    kind: Optional[SpeechKind] = None
    transcript_tsv: Optional[str] = Field(
        default=None,
        sa_column=Column(TSVECTOR, Computed("to_tsvector('english'::regconfig, transcript)", persisted=True)),
    )
    sitting_date: datetime
    report_type: str
    column_start: Optional[int] = None
    column_note: Optional[ColumnNote] = None
    column_suggested: Optional[int] = None

    report_id: int = Field(foreign_key="report.id", index=True)
    report: Report = Relationship(back_populates="speeches")
    speaker_id: Optional[int] = Field(default=None, foreign_key="speaker.id")
