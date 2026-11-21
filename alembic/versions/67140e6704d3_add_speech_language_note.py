"""add speech language note

Revision ID: 67140e6704d3
Revises: b4e8d2f6a1c3
Create Date: 2026-11-21 12:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "67140e6704d3"
down_revision: Optional[Union[str, Sequence[str]]] = "b4e8d2f6a1c3"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.add_column(
        "speech",
        sa.Column("language_note", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("speech", "language_note")
