from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.ministry  # noqa: F401 registers Ministry so the foreign key resolves


class MinistrySeeAlso(SQLModel, table=True):
    __tablename__ = "ministry_see_also"
    __table_args__ = (
        UniqueConstraint(
            "ministry_id", "see_also_ministry_id", name="uq_ministry_see_also_pair"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    note: str
    source_url: str

    ministry_id: int = Field(foreign_key="ministry.id")
    see_also_ministry_id: int = Field(foreign_key="ministry.id")
