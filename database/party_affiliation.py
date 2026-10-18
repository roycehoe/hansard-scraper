from datetime import date
from typing import Optional

from sqlmodel import Field, SQLModel

import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves
from enums import DatePrecision


class PartyAffiliation(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    party: str
    started_on: date
    started_on_precision: DatePrecision
    event: str
    source_url: str

    speaker_id: int = Field(foreign_key="speaker.id", index=True)
