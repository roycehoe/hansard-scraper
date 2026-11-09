from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class Ministry(SQLModel, table=True):
    __tablename__ = "ministry"
    __table_args__ = (UniqueConstraint("name", name="uq_ministry_name"),)

    id: Optional[int] = Field(default=None, primary_key=True)

    name: str
