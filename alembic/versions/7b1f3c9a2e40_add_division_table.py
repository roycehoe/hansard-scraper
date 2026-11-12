"""add division table

Revision ID: 7b1f3c9a2e40
Revises: e3b7c1d94a62
Create Date: 2026-11-09 15:30:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7b1f3c9a2e40"
down_revision: Optional[Union[str, Sequence[str]]] = "e3b7c1d94a62"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_DIVISION_COUNT_SOURCE_NAMES = ("PRINTED_LINE", "SPOKEN_TOTAL", "MINUTES")
_DIVISION_LIST_STATUS_NAMES = (
    "NOT_PRINTED",
    "STORED",
    "COUNTS_DISAGREE",
    "LAYOUT_UNREADABLE",
)


def upgrade() -> None:
    postgresql.ENUM(*_DIVISION_COUNT_SOURCE_NAMES, name="divisioncountsource").create(
        op.get_bind()
    )
    postgresql.ENUM(*_DIVISION_LIST_STATUS_NAMES, name="divisionliststatus").create(
        op.get_bind()
    )
    op.create_table(
        "division",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sitting_date", sa.Date(), nullable=False),
        sa.Column("parliament_number", sa.Integer(), nullable=False),
        sa.Column("report_division_number", sa.Integer(), nullable=True),
        sa.Column("speech_ordinal", sa.Integer(), nullable=True),
        sa.Column(
            "count_source",
            postgresql.ENUM(
                *_DIVISION_COUNT_SOURCE_NAMES,
                name="divisioncountsource",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("printed_counts", sa.Text(), nullable=False),
        sa.Column("ayes", sa.Integer(), nullable=True),
        sa.Column("noes", sa.Integer(), nullable=True),
        sa.Column("abstentions", sa.Integer(), nullable=True),
        sa.Column("absent", sa.Integer(), nullable=True),
        sa.Column("paired", sa.Integer(), nullable=True),
        sa.Column(
            "list_status",
            postgresql.ENUM(
                *_DIVISION_LIST_STATUS_NAMES,
                name="divisionliststatus",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("printed_list", sa.Text(), nullable=True),
        sa.Column("sprs_report_id", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["sprs_report_id"], ["report.report_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sprs_report_id",
            "report_division_number",
            name="uq_division_sprs_report_id_report_division_number",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index("ix_division_sitting_date", "division", ["sitting_date"])
    op.create_index("ix_division_sprs_report_id", "division", ["sprs_report_id"])


def downgrade() -> None:
    op.drop_index("ix_division_sprs_report_id", table_name="division")
    op.drop_index("ix_division_sitting_date", table_name="division")
    op.drop_table("division")
    postgresql.ENUM(name="divisionliststatus").drop(op.get_bind())
    postgresql.ENUM(name="divisioncountsource").drop(op.get_bind())
