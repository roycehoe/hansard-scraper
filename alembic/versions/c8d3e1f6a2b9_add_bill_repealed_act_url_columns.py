"""add bill repealed act url columns

Revision ID: c8d3e1f6a2b9
Revises: b7c2d9e4f1a3
Create Date: 2026-11-08 22:30:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c8d3e1f6a2b9"
down_revision: Optional[Union[str, Sequence[str]]] = "b7c2d9e4f1a3"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_REPEALED_ACT_URL_SOURCE_NAMES = ("REPEALED_ACTS_LISTING",)


def upgrade() -> None:
    postgresql.ENUM(
        *_REPEALED_ACT_URL_SOURCE_NAMES, name="repealedacturlsource"
    ).create(op.get_bind())
    op.add_column("bill", sa.Column("repealed_act_url", sa.Text(), nullable=True))
    op.add_column(
        "bill",
        sa.Column(
            "repealed_act_url_source",
            postgresql.ENUM(
                *_REPEALED_ACT_URL_SOURCE_NAMES,
                name="repealedacturlsource",
                create_type=False,
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("bill", "repealed_act_url_source")
    op.drop_column("bill", "repealed_act_url")
    postgresql.ENUM(name="repealedacturlsource").drop(op.get_bind())
