"""add raw sitting list columns

Revision ID: e5b9c3d7a2f4
Revises: a6d3f1b8c2e5
Create Date: 2026-11-13 06:10:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e5b9c3d7a2f4"
down_revision: Optional[Union[str, Sequence[str]]] = "a6d3f1b8c2e5"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_LIST_COLUMNS = ("sections", "annexures", "vernaculars", "a2b")


def upgrade() -> None:
    for column in _LIST_COLUMNS:
        op.add_column(
            "hansardsittingdateresponse",
            sa.Column(column, sa.Text(), nullable=True),
        )


def downgrade() -> None:
    for column in reversed(_LIST_COLUMNS):
        op.drop_column("hansardsittingdateresponse", column)
