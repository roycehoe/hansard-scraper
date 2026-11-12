"""add sitting span table

Revision ID: b4e8d2f6a915
Revises: a6d3f1b8c2e5
Create Date: 2026-11-12 22:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b4e8d2f6a915"
down_revision: Optional[Union[str, Sequence[str]]] = "a6d3f1b8c2e5"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.create_table(
        "sitting_span",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("first_sitting_date", sa.Date(), nullable=False),
        sa.Column("last_sitting_date", sa.Date(), nullable=False),
        sa.Column("sitting_count", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("speaker_id", name="uq_sitting_span_speaker_id"),
    )


def downgrade() -> None:
    op.drop_table("sitting_span")
