from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.person  # noqa: F401 registers Person so the foreign key resolves
from enums import PersonNameSpellingKind


class PersonNameSpelling(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint(
            "person_id", "ordinal", name="uq_personnamespelling_person_id_ordinal"
        ),
        UniqueConstraint(
            "person_id", "spelling", name="uq_personnamespelling_person_id_spelling"
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    spelling: str
    kind: PersonNameSpellingKind
    note: str

    person_id: int = Field(foreign_key="person.id")
