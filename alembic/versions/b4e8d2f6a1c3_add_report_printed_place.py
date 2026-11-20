"""add report printed place

Revision ID: b4e8d2f6a1c3
Revises: e5b9c3d7a2f4
Create Date: 2026-11-20 09:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b4e8d2f6a1c3"
down_revision: Optional[Union[str, Sequence[str]]] = "e5b9c3d7a2f4"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_PRINTED_PLACE_RULE_NAMES = (
    "SECTION_TEXT",
    "SECTION_TITLE",
    "SECTION_TITLE_AND_SUBTITLE",
    "FULL_TEXT_RUN",
    "ASSENT_FIRST",
    "NOT_PLACED",
)


def upgrade() -> None:
    postgresql.ENUM(*_PRINTED_PLACE_RULE_NAMES, name="printedplacerule").create(
        op.get_bind()
    )
    op.add_column("report", sa.Column("printed_place", sa.Integer(), nullable=True))
    op.add_column(
        "report",
        sa.Column(
            "printed_place_rule",
            postgresql.ENUM(
                *_PRINTED_PLACE_RULE_NAMES, name="printedplacerule", create_type=False
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("report", "printed_place_rule")
    op.drop_column("report", "printed_place")
    postgresql.ENUM(name="printedplacerule").drop(op.get_bind())
