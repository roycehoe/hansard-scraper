"""add minutes division and division vote tables

Revision ID: c41b7e2f9a06
Revises: 3e8a6d15c2f7
Create Date: 2026-11-09 18:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c41b7e2f9a06"
down_revision: Optional[Union[str, Sequence[str]]] = "3e8a6d15c2f7"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_MINUTES_DIVISION_PAIRING_NAMES = (
    "PAIRED",
    "NO_MATCHING_DIVISION",
    "UNEQUAL_NUMBER",
    "TIED",
    "ABSTENTIONS_DIFFER",
)
_DIVISION_VOTE_LIST_SOURCE_NAMES = ("MINUTES", "HANSARD")
_DIVISION_VOTE_CHOICE_NAMES = ("AYE", "NO", "ABSTAIN", "ABSENT", "PAIRED")
_DIVISION_VOTE_NAME_RULE_NAMES = (
    "EXACT",
    "INVERTED",
    "BIN_FREE",
    "SAME_WORDS",
    "HAND_LIST",
)


def upgrade() -> None:
    postgresql.ENUM(
        *_MINUTES_DIVISION_PAIRING_NAMES, name="minutesdivisionpairing"
    ).create(op.get_bind())
    postgresql.ENUM(
        *_DIVISION_VOTE_LIST_SOURCE_NAMES, name="divisionvotelistsource"
    ).create(op.get_bind())
    postgresql.ENUM(*_DIVISION_VOTE_CHOICE_NAMES, name="divisionvotechoice").create(
        op.get_bind()
    )
    postgresql.ENUM(
        *_DIVISION_VOTE_NAME_RULE_NAMES, name="divisionvotenamerule"
    ).create(op.get_bind())
    op.create_table(
        "minutes_division",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("printed_counts", sa.Text(), nullable=False),
        sa.Column("ayes", sa.Integer(), nullable=False),
        sa.Column("noes", sa.Integer(), nullable=False),
        sa.Column("abstentions", sa.Integer(), nullable=True),
        sa.Column("printed_list", sa.Text(), nullable=True),
        sa.Column(
            "list_status",
            postgresql.ENUM(name="divisionliststatus", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "pairing",
            postgresql.ENUM(
                *_MINUTES_DIVISION_PAIRING_NAMES,
                name="minutesdivisionpairing",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("minutes_id", sa.Integer(), nullable=False),
        sa.Column("division_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["minutes_id"], ["minutes.id"]),
        sa.ForeignKeyConstraint(["division_id"], ["division.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "minutes_id", "ordinal", name="uq_minutes_division_minutes_id_ordinal"
        ),
    )
    op.create_index(
        "ix_minutes_division_minutes_id", "minutes_division", ["minutes_id"]
    )
    op.create_index(
        "ix_minutes_division_division_id", "minutes_division", ["division_id"]
    )
    op.create_table(
        "division_vote",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("printed_name", sa.Text(), nullable=False),
        sa.Column(
            "vote_choice",
            postgresql.ENUM(
                *_DIVISION_VOTE_CHOICE_NAMES,
                name="divisionvotechoice",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "list_source",
            postgresql.ENUM(
                *_DIVISION_VOTE_LIST_SOURCE_NAMES,
                name="divisionvotelistsource",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "name_rule",
            postgresql.ENUM(
                *_DIVISION_VOTE_NAME_RULE_NAMES,
                name="divisionvotenamerule",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("party", sa.Text(), nullable=True),
        sa.Column("is_party_uncertain", sa.Boolean(), nullable=False),
        sa.Column("division_id", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["division_id"], ["division.id"]),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "division_id",
            "list_source",
            "ordinal",
            name="uq_division_vote_division_id_list_source_ordinal",
        ),
    )
    op.create_index("ix_division_vote_division_id", "division_vote", ["division_id"])
    op.create_index("ix_division_vote_speaker_id", "division_vote", ["speaker_id"])


def downgrade() -> None:
    op.drop_index("ix_division_vote_speaker_id", table_name="division_vote")
    op.drop_index("ix_division_vote_division_id", table_name="division_vote")
    op.drop_index("ix_minutes_division_division_id", table_name="minutes_division")
    op.drop_index("ix_minutes_division_minutes_id", table_name="minutes_division")
    op.drop_table("division_vote")
    op.drop_table("minutes_division")
    postgresql.ENUM(name="divisionvotenamerule").drop(op.get_bind())
    postgresql.ENUM(name="divisionvotechoice").drop(op.get_bind())
    postgresql.ENUM(name="divisionvotelistsource").drop(op.get_bind())
    postgresql.ENUM(name="minutesdivisionpairing").drop(op.get_bind())
