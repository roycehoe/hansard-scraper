"""add chair call to the report asker source

Revision ID: a4c8e1d27f93
Revises: b50219e27a8f
Create Date: 2026-11-04 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4c8e1d27f93"
down_revision: Union[str, Sequence[str], None] = "b50219e27a8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE reportaskersource ADD VALUE IF NOT EXISTS 'CHAIR_CALL'")


def downgrade() -> None:
    # NOTE: postgres cannot drop one value from an enum type
    pass
