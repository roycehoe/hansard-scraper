from datetime import date
from typing import Optional

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves
import database.speech  # noqa: F401 registers Report and Speech so the foreign key resolves
from enums import DatePrecision


class PartyAffiliation(SQLModel, table=True):
    __table_args__ = (CheckConstraint("num_nonnulls(source_url, source_report_id) = 1", name="ck_partyaffiliation_exactly_one_source"),)

    id: Optional[int] = Field(default=None, primary_key=True)

    party: str
    started_on: date
    started_on_precision: DatePrecision
    event: str
    source_url: Optional[str] = None

    is_started_on_upper_bound: bool

    source_report_id: Optional[int] = Field(default=None, foreign_key="report.id", index=True)
    speaker_id: int = Field(foreign_key="speaker.id", index=True)
