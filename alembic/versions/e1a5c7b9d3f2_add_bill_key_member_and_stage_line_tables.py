"""add bill key, member and stage line tables

Revision ID: e1a5c7b9d3f2
Revises: e7b2c4d9f1a6
Create Date: 2026-11-09 09:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e1a5c7b9d3f2"
down_revision: Optional[Union[str, Sequence[str]]] = "e7b2c4d9f1a6"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_BILL_STAGE_NAMES = (
    "FIRST_READING",
    "SECOND_READING_ORDER",
    "SECOND_READING_AGREED",
    "THIRD_READING",
)


def upgrade() -> None:
    postgresql.ENUM(*_BILL_STAGE_NAMES, name="billstage").create(op.get_bind())
    op.create_table(
        "billkey",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("act_count", sa.Integer(), nullable=False),
        sa.Column("bill_key", sa.Text(), nullable=False),
        sa.Column("bill_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["bill_key"], ["report.report_id"]),
        sa.ForeignKeyConstraint(["bill_id"], ["bill.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bill_key"),
        sa.UniqueConstraint("bill_id"),
    )
    op.create_table(
        "billreportspeaker",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("speech_count", sa.Integer(), nullable=False),
        sa.Column("first_ordinal", sa.Integer(), nullable=False),
        sa.Column("printed_speaker", sa.Text(), nullable=False),
        sa.Column("sprs_report_id", sa.Text(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["sprs_report_id"], ["report.report_id"]),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sprs_report_id",
            "speaker_id",
            name="uq_billreportspeaker_sprs_report_id_speaker_id",
        ),
    )
    op.create_index(
        "ix_billreportspeaker_sprs_report_id", "billreportspeaker", ["sprs_report_id"]
    )
    op.create_index(
        "ix_billreportspeaker_speaker_id", "billreportspeaker", ["speaker_id"]
    )
    op.create_table(
        "billstageline",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "stage",
            postgresql.ENUM(*_BILL_STAGE_NAMES, name="billstage", create_type=False),
            nullable=False,
        ),
        sa.Column("printed_text", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("sprs_report_id", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["sprs_report_id"], ["report.report_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sprs_report_id",
            "ordinal",
            "stage",
            name="uq_billstageline_sprs_report_id_ordinal_stage",
        ),
    )
    op.create_index(
        "ix_billstageline_sprs_report_id", "billstageline", ["sprs_report_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_billstageline_sprs_report_id", table_name="billstageline")
    op.drop_table("billstageline")
    op.drop_index("ix_billreportspeaker_speaker_id", table_name="billreportspeaker")
    op.drop_index("ix_billreportspeaker_sprs_report_id", table_name="billreportspeaker")
    op.drop_table("billreportspeaker")
    op.drop_table("billkey")
    postgresql.ENUM(name="billstage").drop(op.get_bind())
