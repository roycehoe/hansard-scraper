from datetime import date
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves


class SeatHolding(SQLModel, table=True):
    __tablename__ = "seat_holding"
    __table_args__ = (
        UniqueConstraint(
            "division_key", "speaker_id", name="uq_seat_holding_division_key_speaker_id"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    division_key: str
    location_name: str
    first_sitting_date: date
    last_sitting_date: date
    sitting_count: int

    speaker_id: int = Field(foreign_key="speaker.id", index=True)
