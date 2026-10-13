from typing import Optional

from sqlmodel import Field, SQLModel

import database.person  # noqa: F401


class Speaker(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    party: str
    is_legislative_assembly: bool
    parliament_number: int
    comments: Optional[str] = None
    is_member: bool = True  # False for heads of state, who speak in the House but are not members
    person_id: Optional[int] = Field(default=None, foreign_key="person.id", index=True)
