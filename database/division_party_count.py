from typing import Optional

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

import database.division  # noqa: F401 registers Division so the foreign key resolves
from enums import DivisionVoteChoice, DivisionVoteListSource


class DivisionPartyCount(SQLModel, table=True):
    __tablename__ = "division_party_count"
    __table_args__ = (
        UniqueConstraint(
            "division_id",
            "vote_choice",
            "party",
            name="uq_division_party_count_division_id_vote_choice_party",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            "vote_choice IN ('AYE', 'NO', 'ABSTAIN')",
            name="ck_division_party_count_vote_choice",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    member_count: int
    uncertain_member_count: int
    party: Optional[str] = None
    list_source: DivisionVoteListSource
    vote_choice: DivisionVoteChoice

    division_id: int = Field(foreign_key="division.id", index=True)
