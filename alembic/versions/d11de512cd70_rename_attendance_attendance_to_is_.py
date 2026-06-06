"""rename attendance.attendance to is_present

Revision ID: d11de512cd70
Revises: 5685ce857b21
Create Date: 2026-06-06 11:10:42.435737

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd11de512cd70'
down_revision: Union[str, Sequence[str], None] = '5685ce857b21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('attendance', 'attendance', new_column_name='is_present')


def downgrade() -> None:
    op.alter_column('attendance', 'is_present', new_column_name='attendance')
