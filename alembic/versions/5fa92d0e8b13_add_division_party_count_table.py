"""add division party count table

Revision ID: 5fa92d0e8b13
Revises: c41b7e2f9a06
Create Date: 2026-11-12 09:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "5fa92d0e8b13"
down_revision: Optional[Union[str, Sequence[str]]] = "c41b7e2f9a06"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.create_table(
        "division_party_count",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("uncertain_member_count", sa.Integer(), nullable=False),
        sa.Column("party", sa.Text(), nullable=True),
        sa.Column(
            "list_source",
            postgresql.ENUM(name="divisionvotelistsource", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "vote_choice",
            postgresql.ENUM(name="divisionvotechoice", create_type=False),
            nullable=False,
        ),
        sa.Column("division_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["division_id"], ["division.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "division_id",
            "vote_choice",
            "party",
            name="uq_division_party_count_division_id_vote_choice_party",
            postgresql_nulls_not_distinct=True,
        ),
        sa.CheckConstraint(
            "vote_choice IN ('AYE', 'NO', 'ABSTAIN')",
            name="ck_division_party_count_vote_choice",
        ),
    )
    op.create_index(
        "ix_division_party_count_division_id", "division_party_count", ["division_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_division_party_count_division_id", table_name="division_party_count"
    )
    op.drop_table("division_party_count")
