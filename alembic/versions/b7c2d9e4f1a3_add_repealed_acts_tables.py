"""add repealed acts tables

Revision ID: b7c2d9e4f1a3
Revises: a9d4e7f2c1b8
Create Date: 2026-11-08 22:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b7c2d9e4f1a3"
down_revision: Optional[Union[str, Sequence[str]]] = "a9d4e7f2c1b8"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.create_table(
        "repealedactscapture",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("archive_timestamp", sa.Text(), nullable=False),
        sa.Column("capture_url", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capture_url"),
    )
    op.create_table(
        "repealedactentry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("printed_title", sa.Text(), nullable=False),
        sa.Column("printed_chapter", sa.Text(), nullable=True),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("sso_code", sa.Text(), nullable=False),
        sa.Column("enactment_year", sa.Integer(), nullable=True),
        sa.Column("repeal_date", sa.Date(), nullable=False),
        sa.Column("last_version_date", sa.Date(), nullable=False),
        sa.Column("capture_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["capture_id"], ["repealedactscapture.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sso_code"),
    )
    op.create_index(
        "ix_repealedactentry_capture_id", "repealedactentry", ["capture_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_repealedactentry_capture_id", table_name="repealedactentry")
    op.drop_table("repealedactentry")
    op.drop_table("repealedactscapture")
