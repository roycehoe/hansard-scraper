from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.division  # noqa: F401 registers Division so the foreign key resolves
import database.minutes  # noqa: F401 registers Minutes so the foreign key resolves
from enums import DivisionListStatus, MinutesDivisionPairing


class MinutesDivision(SQLModel, table=True):
    __tablename__ = "minutes_division"
    __table_args__ = (
        UniqueConstraint(
            "minutes_id", "ordinal", name="uq_minutes_division_minutes_id_ordinal"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    printed_counts: str
    ayes: int
    noes: int
    abstentions: Optional[int] = None
    printed_list: Optional[str] = None

    list_status: DivisionListStatus
    pairing: MinutesDivisionPairing

    minutes_id: int = Field(foreign_key="minutes.id", index=True)
    division_id: int = Field(foreign_key="division.id", index=True)
