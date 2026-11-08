"""add egazette supplement table

Revision ID: e8a2b4c6d1f9
Revises: c4d8e2a1b7f3
Create Date: 2026-11-08 12:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e8a2b4c6d1f9"
down_revision: Optional[Union[str, Sequence[str]]] = "c4d8e2a1b7f3"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_EGAZETTE_SUPPLEMENT_KIND_NAMES = ("BILLS", "ACTS")
_BILL_LINK_SOURCE_NAMES = (
    "FIRST_READING_DATE",
    "THIRD_READING_DATE",
    "SECOND_READING_DATE",
    "LOOSE_TITLE_READING_DATES",
    "SIMILAR_TITLE_READING_DATES",
    "HAND_KEPT",
)


def upgrade() -> None:
    postgresql.ENUM(
        *_EGAZETTE_SUPPLEMENT_KIND_NAMES, name="egazettesupplementkind"
    ).create(op.get_bind())
    op.create_table(
        "egazettesupplement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column(
            "supplement_kind",
            postgresql.ENUM(
                *_EGAZETTE_SUPPLEMENT_KIND_NAMES,
                name="egazettesupplementkind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("printed_title", sa.Text(), nullable=False),
        sa.Column("printed_bill_number", sa.Text(), nullable=False),
        sa.Column("bill_number", sa.Text(), nullable=False),
        sa.Column("first_reading_date", sa.Date(), nullable=False),
        sa.Column("passing_date", sa.Date(), nullable=True),
        sa.Column("printed_act_number", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "bill_link_source",
            postgresql.ENUM(
                *_BILL_LINK_SOURCE_NAMES, name="billlinksource", create_type=False
            ),
            nullable=True,
        ),
        sa.Column("bill_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["bill_id"], ["bill.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_egazettesupplement_bill_id", "egazettesupplement", ["bill_id"])


def downgrade() -> None:
    op.drop_index("ix_egazettesupplement_bill_id", table_name="egazettesupplement")
    op.drop_table("egazettesupplement")
    postgresql.ENUM(name="egazettesupplementkind").drop(op.get_bind())
