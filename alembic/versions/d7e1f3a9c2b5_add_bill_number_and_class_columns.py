"""add bill number and class columns

Revision ID: d7e1f3a9c2b5
Revises: e8a2b4c6d1f9
Create Date: 2026-11-08 15:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d7e1f3a9c2b5"
down_revision: Optional[Union[str, Sequence[str]]] = "e8a2b4c6d1f9"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_BILL_CLASS_NAMES = ("SUPPLY", "REPEAL")
_BILL_NUMBER_SOURCE_NAMES = ("BILLS_SUPPLEMENT_LISTING", "EGAZETTE_BILLS_SUPPLEMENT")


def upgrade() -> None:
    postgresql.ENUM(*_BILL_CLASS_NAMES, name="billclass").create(op.get_bind())
    postgresql.ENUM(*_BILL_NUMBER_SOURCE_NAMES, name="billnumbersource").create(
        op.get_bind()
    )
    op.add_column("bill", sa.Column("bill_number", sa.Text(), nullable=True))
    op.add_column(
        "bill",
        sa.Column(
            "bill_number_source",
            postgresql.ENUM(
                *_BILL_NUMBER_SOURCE_NAMES, name="billnumbersource", create_type=False
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "bill",
        sa.Column(
            "bill_class",
            postgresql.ENUM(*_BILL_CLASS_NAMES, name="billclass", create_type=False),
            nullable=True,
        ),
    )
    op.create_index("ix_bill_bill_number", "bill", ["bill_number"])
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE billlinksource ADD VALUE IF NOT EXISTS 'BILL_NUMBER_PASSING_DATE'"
        )


def downgrade() -> None:
    op.drop_index("ix_bill_bill_number", table_name="bill")
    op.drop_column("bill", "bill_class")
    op.drop_column("bill", "bill_number_source")
    op.drop_column("bill", "bill_number")
    postgresql.ENUM(name="billnumbersource").drop(op.get_bind())
    postgresql.ENUM(name="billclass").drop(op.get_bind())
    op.execute("ALTER TYPE billlinksource RENAME TO billlinksource_with_passing_date")
    op.execute(
        "CREATE TYPE billlinksource AS ENUM ('FIRST_READING_DATE', "
        "'THIRD_READING_DATE', 'SECOND_READING_DATE', 'LOOSE_TITLE_READING_DATES', "
        "'SIMILAR_TITLE_READING_DATES', 'HAND_KEPT')"
    )
    op.execute(
        "ALTER TABLE acthistoryentry ALTER COLUMN bill_link_source "
        "TYPE billlinksource USING bill_link_source::text::billlinksource"
    )
    op.execute(
        "ALTER TABLE egazettesupplement ALTER COLUMN bill_link_source "
        "TYPE billlinksource USING bill_link_source::text::billlinksource"
    )
    op.execute("DROP TYPE billlinksource_with_passing_date")
