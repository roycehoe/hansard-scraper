from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.ministry  # noqa: F401 registers Ministry so the foreign key resolves
from enums import OfficeTitleMinistrySource


class OfficeTitleMinistry(SQLModel, table=True):
    __tablename__ = "office_title_ministry"
    __table_args__ = (
        UniqueConstraint(
            "office_printed",
            "ministry_id",
            name="uq_office_title_ministry_office_printed_ministry_id",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    office_printed: str = Field(index=True)
    ordinal: int
    source: OfficeTitleMinistrySource

    ministry_id: int = Field(foreign_key="ministry.id", index=True)
