from typing import Optional

from sqlmodel import Field, SQLModel

import database.person  # noqa: F401 registers Person so the foreign key resolves


class Speaker(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    party: str
    is_legislative_assembly: bool
    parliament_number: int
    comments: Optional[str] = None
    # NOTE: False for heads of state, who speak in the House but are not members
    is_member: bool = True
    person_id: Optional[int] = Field(default=None, foreign_key="person.id", index=True)
