"""add minutes file bytes

Revision ID: a6d3f1b8c2e5
Revises: 5fa92d0e8b13
Create Date: 2026-11-12 14:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a6d3f1b8c2e5"
down_revision: Optional[Union[str, Sequence[str]]] = "5fa92d0e8b13"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column("minutes", sa.Column("file_bytes", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("minutes", "file_bytes")
