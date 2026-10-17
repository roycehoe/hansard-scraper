"""add a unique constraint on attendance sitting and speaker

Revision ID: 641870b78b3f
Revises: f2b8d4a6c913
Create Date: 2026-10-17 11:53:48.261442

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '641870b78b3f'
down_revision: Union[str, Sequence[str], None] = 'f2b8d4a6c913'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT_NAME = 'uq_attendance_sitting_id_speaker_id'


def upgrade() -> None:
    op.create_unique_constraint(_CONSTRAINT_NAME, 'attendance', ['sitting_id', 'speaker_id'])


def downgrade() -> None:
    op.drop_constraint(_CONSTRAINT_NAME, 'attendance', type_='unique')
