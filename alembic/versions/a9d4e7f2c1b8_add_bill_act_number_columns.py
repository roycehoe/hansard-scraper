"""add bill act number columns

Revision ID: a9d4e7f2c1b8
Revises: f3a7c9e1b2d4
Create Date: 2026-11-08 21:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a9d4e7f2c1b8"
down_revision: Optional[Union[str, Sequence[str]]] = "f3a7c9e1b2d4"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_ACT_NUMBER_SOURCE_NAMES = ("ACTS_SUPPLEMENT_LISTING",)


def upgrade() -> None:
    postgresql.ENUM(*_ACT_NUMBER_SOURCE_NAMES, name="actnumbersource").create(
        op.get_bind()
    )
    op.add_column("bill", sa.Column("act_number", sa.Text(), nullable=True))
    op.add_column(
        "bill",
        sa.Column(
            "act_number_source",
            postgresql.ENUM(
                *_ACT_NUMBER_SOURCE_NAMES, name="actnumbersource", create_type=False
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("bill", "act_number_source")
    op.drop_column("bill", "act_number")
    postgresql.ENUM(name="actnumbersource").drop(op.get_bind())
