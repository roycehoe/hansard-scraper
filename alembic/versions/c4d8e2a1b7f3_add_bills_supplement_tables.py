"""add bills supplement tables

Revision ID: c4d8e2a1b7f3
Revises: 5f49ebce7f19
Create Date: 2026-11-08 12:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c4d8e2a1b7f3"
down_revision: Optional[Union[str, Sequence[str]]] = "5f49ebce7f19"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.create_table(
        "billssupplementcapture",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("archive_timestamp", sa.Text(), nullable=False),
        sa.Column("capture_url", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capture_url"),
    )
    op.create_table(
        "billssupplemententry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("printed_title", sa.Text(), nullable=False),
        sa.Column("printed_number", sa.Text(), nullable=False),
        sa.Column("link", sa.Text(), nullable=False),
        sa.Column("pdf_link", sa.Text(), nullable=True),
        sa.Column("pdf_size", sa.Text(), nullable=True),
        sa.Column("bill_number", sa.Text(), nullable=False),
        sa.Column("publication_date", sa.Date(), nullable=False),
        sa.Column("capture_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["capture_id"], ["billssupplementcapture.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bill_number", "link", name="uq_billssupplemententry_bill_number_link"
        ),
    )
    op.create_index(
        "ix_billssupplemententry_capture_id", "billssupplemententry", ["capture_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_billssupplemententry_capture_id", table_name="billssupplemententry"
    )
    op.drop_table("billssupplemententry")
    op.drop_table("billssupplementcapture")
