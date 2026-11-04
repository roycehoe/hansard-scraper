"""add bill and act tables

Revision ID: 4b9e7c2d1a58
Revises: 82478ba59541
Create Date: 2026-11-04 18:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4b9e7c2d1a58"
down_revision: Union[str, Sequence[str], None] = "82478ba59541"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACT_HISTORY_ENTRY_KIND_NAMES = (
    "ACT",
    "ORDINANCE",
    "REVISED_EDITION",
    "SUBSIDIARY_LEGISLATION",
    "OTHER",
)
_BILL_LINK_SOURCE_NAMES = (
    "FIRST_READING_DATE",
    "THIRD_READING_DATE",
    "SECOND_READING_DATE",
)


def upgrade() -> None:
    postgresql.ENUM(*_ACT_HISTORY_ENTRY_KIND_NAMES, name="acthistoryentrykind").create(
        op.get_bind()
    )
    postgresql.ENUM(*_BILL_LINK_SOURCE_NAMES, name="billlinksource").create(
        op.get_bind()
    )
    op.create_table(
        "bill",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_key", sa.Text(), nullable=False),
        sa.Column("first_sitting_date", sa.DateTime(), nullable=False),
        sa.Column("last_sitting_date", sa.DateTime(), nullable=False),
        sa.Column("is_passed", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_bill_title_key", "bill", ["title_key"])
    op.create_table(
        "billreport",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bill_id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["bill_id"], ["bill.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["report.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bill_id", "report_id", name="uq_billreport_bill_id_report_id"
        ),
    )
    op.create_index("ix_billreport_bill_id", "billreport", ["bill_id"])
    op.create_index("ix_billreport_report_id", "billreport", ["report_id"])
    op.create_table(
        "act",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sso_code", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sso_code"),
    )
    op.create_table(
        "acthistoryentry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("printed_text", sa.Text(), nullable=False),
        sa.Column("printed_law_number", sa.Text(), nullable=False),
        sa.Column("printed_title", sa.Text(), nullable=False),
        sa.Column("printed_bill_number", sa.Text(), nullable=True),
        sa.Column("first_reading_date", sa.Date(), nullable=True),
        sa.Column("second_reading_date", sa.Date(), nullable=True),
        sa.Column("third_reading_date", sa.Date(), nullable=True),
        sa.Column("commencement_date", sa.Date(), nullable=True),
        sa.Column(
            "kind",
            postgresql.ENUM(
                *_ACT_HISTORY_ENTRY_KIND_NAMES,
                name="acthistoryentrykind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "bill_link_source",
            postgresql.ENUM(
                *_BILL_LINK_SOURCE_NAMES, name="billlinksource", create_type=False
            ),
            nullable=True,
        ),
        sa.Column("act_id", sa.Integer(), nullable=False),
        sa.Column("bill_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["act_id"], ["act.id"]),
        sa.ForeignKeyConstraint(["bill_id"], ["bill.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "act_id", "ordinal", name="uq_acthistoryentry_act_id_ordinal"
        ),
    )
    op.create_index("ix_acthistoryentry_act_id", "acthistoryentry", ["act_id"])
    op.create_index("ix_acthistoryentry_bill_id", "acthistoryentry", ["bill_id"])


def downgrade() -> None:
    op.drop_index("ix_acthistoryentry_bill_id", table_name="acthistoryentry")
    op.drop_index("ix_acthistoryentry_act_id", table_name="acthistoryentry")
    op.drop_table("acthistoryentry")
    op.drop_table("act")
    op.drop_index("ix_billreport_report_id", table_name="billreport")
    op.drop_index("ix_billreport_bill_id", table_name="billreport")
    op.drop_table("billreport")
    op.drop_index("ix_bill_title_key", table_name="bill")
    op.drop_table("bill")
    postgresql.ENUM(name="billlinksource").drop(op.get_bind())
    postgresql.ENUM(name="acthistoryentrykind").drop(op.get_bind())
