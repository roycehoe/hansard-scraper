"""rename attendance.mp_name to speaker_name

Revision ID: 5685ce857b21
Revises: ace11f636657
Create Date: 2026-06-01 18:09:01.785011

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '5685ce857b21'
down_revision: Union[str, Sequence[str], None] = 'ace11f636657'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('attendance', 'mp_name', new_column_name='speaker_name')


def downgrade() -> None:
    op.alter_column('attendance', 'speaker_name', new_column_name='mp_name')
