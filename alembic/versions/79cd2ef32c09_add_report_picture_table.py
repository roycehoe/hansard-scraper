"""add report picture table

Revision ID: 79cd2ef32c09
Revises: 67140e6704d3
Create Date: 2026-11-21 15:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "79cd2ef32c09"
down_revision: Optional[Union[str, Sequence[str]]] = "67140e6704d3"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_PICTURE_KIND_NAMES = ("TABLE", "DIVISION_LIST", "OTHER")


def upgrade() -> None:
    postgresql.ENUM(*_PICTURE_KIND_NAMES, name="picturekind").create(op.get_bind())
    op.create_table(
        "report_picture",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                *_PICTURE_KIND_NAMES, name="picturekind", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("picture_index", sa.Integer(), nullable=False),
        sa.Column("content_offset", sa.Integer(), nullable=False),
        sa.Column("follows_ordinal", sa.Integer(), nullable=True),
        sa.Column("media_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("picture_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("typed_copy", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["report_id"], ["report.id"], name="report_picture_report_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_id",
            "picture_index",
            name="uq_report_picture_report_id_picture_index",
        ),
    )
    op.create_index("ix_report_picture_report_id", "report_picture", ["report_id"])
    op.create_index("ix_report_picture_sha256", "report_picture", ["sha256"])


def downgrade() -> None:
    op.drop_index("ix_report_picture_sha256", table_name="report_picture")
    op.drop_index("ix_report_picture_report_id", table_name="report_picture")
    op.drop_table("report_picture")
    postgresql.ENUM(name="picturekind").drop(op.get_bind())
