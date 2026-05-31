from typing import Optional

from sqlmodel import Field, SQLModel


class Mp(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    party: str
    is_legislative_assembly: bool
    parliament_number: int
    comments: Optional[str] = None
