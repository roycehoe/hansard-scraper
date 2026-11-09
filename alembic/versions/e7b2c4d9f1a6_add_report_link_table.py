"""add report link table

Revision ID: e7b2c4d9f1a6
Revises: e7b4c2a9f1d3
Create Date: 2026-11-09 09:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e7b2c4d9f1a6"
down_revision: Optional[Union[str, Sequence[str]]] = "e7b4c2a9f1d3"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_REPORT_LINK_TYPE_NAMES = ("CORRECTION", "REPLY", "CONTINUATION")
_REPORT_LINK_RULE_NAMES = (
    "PRINTED_TITLE_ON_PRINTED_DATE",
    "SAME_TITLE_ON_PRINTED_DATE",
    "LAST_PART_ON_PRINTED_DATE",
    "TITLE_KEY_ON_PRINTED_DATE",
    "HAND_KEPT_TITLE_ON_PRINTED_DATE",
)


def upgrade() -> None:
    postgresql.ENUM(*_REPORT_LINK_TYPE_NAMES, name="reportlinktype").create(
        op.get_bind()
    )
    postgresql.ENUM(*_REPORT_LINK_RULE_NAMES, name="reportlinkrule").create(
        op.get_bind()
    )
    op.create_table(
        "report_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "link_type",
            postgresql.ENUM(
                *_REPORT_LINK_TYPE_NAMES, name="reportlinktype", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "rule",
            postgresql.ENUM(
                *_REPORT_LINK_RULE_NAMES, name="reportlinkrule", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("printed_citation", sa.Text(), nullable=False),
        sa.Column(
            "source_report_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column(
            "target_report_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.CheckConstraint(
            "source_report_id <> target_report_id",
            name="ck_report_link_source_differs_from_target",
        ),
        sa.ForeignKeyConstraint(["source_report_id"], ["report.report_id"]),
        sa.ForeignKeyConstraint(["target_report_id"], ["report.report_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_report_id",
            "target_report_id",
            "link_type",
            name="uq_report_link_source_target_type",
        ),
    )
    op.create_index(
        "ix_report_link_target_report_id", "report_link", ["target_report_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_report_link_target_report_id", table_name="report_link")
    op.drop_table("report_link")
    postgresql.ENUM(name="reportlinkrule").drop(op.get_bind())
    postgresql.ENUM(name="reportlinktype").drop(op.get_bind())
