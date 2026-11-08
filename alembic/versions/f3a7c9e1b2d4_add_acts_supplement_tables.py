"""add acts supplement tables

Revision ID: f3a7c9e1b2d4
Revises: d7e1f3a9c2b5
Create Date: 2026-11-08 18:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "f3a7c9e1b2d4"
down_revision: Optional[Union[str, Sequence[str]]] = "d7e1f3a9c2b5"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.create_table(
        "actssupplementcapture",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("archive_timestamp", sa.Text(), nullable=False),
        sa.Column("capture_url", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capture_url"),
    )
    op.create_table(
        "actssupplemententry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("printed_title", sa.Text(), nullable=False),
        sa.Column("printed_number", sa.Text(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("pdf_link", sa.Text(), nullable=True),
        sa.Column("pdf_size", sa.Text(), nullable=True),
        sa.Column("act_number", sa.Text(), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=False),
        sa.Column("capture_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["capture_id"], ["actssupplementcapture.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "act_number", "link", name="uq_actssupplemententry_act_number_link"
        ),
    )
    op.create_index(
        "ix_actssupplemententry_capture_id", "actssupplemententry", ["capture_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_actssupplemententry_capture_id", table_name="actssupplemententry")
    op.drop_table("actssupplemententry")
    op.drop_table("actssupplementcapture")
