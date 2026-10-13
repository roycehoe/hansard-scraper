from typing import Optional

from sqlmodel import Field, SQLModel


class Person(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    canonical_name: str
    basis: Optional[str] = None
    notes: Optional[str] = None
