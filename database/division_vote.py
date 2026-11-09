from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

import database.division  # noqa: F401 registers Division so the foreign key resolves
import database.speaker  # noqa: F401 registers Speaker so the foreign key resolves
from enums import DivisionVoteChoice, DivisionVoteListSource, DivisionVoteNameRule


class DivisionVote(SQLModel, table=True):
    __tablename__ = "division_vote"
    __table_args__ = (
        UniqueConstraint(
            "division_id",
            "list_source",
            "ordinal",
            name="uq_division_vote_division_id_list_source_ordinal",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    ordinal: int
    printed_name: str
    vote_choice: DivisionVoteChoice
    list_source: DivisionVoteListSource
    name_rule: Optional[DivisionVoteNameRule] = None
    party: Optional[str] = None

    is_party_uncertain: bool = False

    division_id: int = Field(foreign_key="division.id", index=True)
    speaker_id: Optional[int] = Field(
        default=None, foreign_key="speaker.id", index=True
    )
