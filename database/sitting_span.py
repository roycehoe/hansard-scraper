from datetime import date
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves


class SittingSpan(SQLModel, table=True):
    __tablename__ = "sitting_span"
    __table_args__ = (
        UniqueConstraint("speaker_id", name="uq_sitting_span_speaker_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    first_sitting_date: date
    last_sitting_date: date
    sitting_count: int

    speaker_id: int = Field(foreign_key="speaker.id")
