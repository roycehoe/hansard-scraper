"""add question number call to the participant role source

Revision ID: 287f3a4e2fdd
Revises: a4c8e1d27f93
Create Date: 2026-11-04 19:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "287f3a4e2fdd"
down_revision: Union[str, Sequence[str], None] = "a4c8e1d27f93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE participantrolesource ADD VALUE IF NOT EXISTS 'QUESTION_NUMBER_CALL'"
    )


def downgrade() -> None:
    # NOTE: postgres cannot drop one value from an enum type
    pass
