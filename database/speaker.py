from typing import Optional

from sqlmodel import Field, SQLModel


class Speaker(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    party: str
    is_legislative_assembly: bool
    parliament_number: int
    comments: Optional[str] = None
