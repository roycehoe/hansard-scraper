"""add report asker table

Revision ID: 52f4f7b77f1f
Revises: 82478ba59541
Create Date: 2026-11-03 22:31:57.584778

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "52f4f7b77f1f"
down_revision: Optional[Union[str, Sequence[str]]] = "82478ba59541"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_REPORT_ASKER_SOURCE_NAMES = (
    "ASKED_LINE",
    "TO_ASK_LINE",
    "STOOD_IN_NAME_LINE",
    "NAME_IN_TEXT",
)


def upgrade() -> None:
    postgresql.ENUM(*_REPORT_ASKER_SOURCE_NAMES, name="reportaskersource").create(
        op.get_bind()
    )
    op.create_table(
        "report_asker",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("printed_name", sa.Text(), nullable=False),
        sa.Column(
            "source",
            postgresql.ENUM(
                *_REPORT_ASKER_SOURCE_NAMES, name="reportaskersource", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("reader_printed_name", sa.Text(), nullable=True),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=True),
        sa.Column("reader_speaker_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["report.id"]),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"]),
        sa.ForeignKeyConstraint(["reader_speaker_id"], ["speaker.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_id", "ordinal", name="uq_report_asker_report_id_ordinal"
        ),
    )
    op.create_index("ix_report_asker_report_id", "report_asker", ["report_id"])
    op.create_index("ix_report_asker_speaker_id", "report_asker", ["speaker_id"])


def downgrade() -> None:
    op.drop_index("ix_report_asker_speaker_id", table_name="report_asker")
    op.drop_index("ix_report_asker_report_id", table_name="report_asker")
    op.drop_table("report_asker")
    postgresql.ENUM(name="reportaskersource").drop(op.get_bind())
