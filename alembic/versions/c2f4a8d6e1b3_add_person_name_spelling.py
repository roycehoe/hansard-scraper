"""add person name spelling table

Revision ID: c2f4a8d6e1b3
Revises: a7d3e9f1b264
Create Date: 2026-11-06 22:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2f4a8d6e1b3"
down_revision: Union[str, Sequence[str], None] = "a7d3e9f1b264"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_KIND_NAMES = ("CANONICAL", "OTHER_SPELLING", "TRANSLITERATION", "OTHER_NAME")


def upgrade() -> None:
    postgresql.ENUM(*_KIND_NAMES, name="personnamespellingkind").create(op.get_bind())
    op.create_table(
        "personnamespelling",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("spelling", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                *_KIND_NAMES, name="personnamespellingkind", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "person_id", "ordinal", name="uq_personnamespelling_person_id_ordinal"
        ),
        sa.UniqueConstraint(
            "person_id", "spelling", name="uq_personnamespelling_person_id_spelling"
        ),
    )


def downgrade() -> None:
    op.drop_table("personnamespelling")
    postgresql.ENUM(name="personnamespellingkind").drop(op.get_bind())
