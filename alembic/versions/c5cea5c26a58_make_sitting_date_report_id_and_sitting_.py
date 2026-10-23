"""make sitting_date, report_id and sitting_id not null

Revision ID: c5cea5c26a58
Revises: 6b3a29f6f809
Create Date: 2026-10-23 15:20:06.872525

"""
from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'c5cea5c26a58'
down_revision: Optional[Union[str, Sequence[str]]] = '6b3a29f6f809'
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    op.alter_column('sitting', 'sitting_date', existing_type=sa.VARCHAR(), nullable=False)
    op.alter_column('speech', 'report_id', existing_type=sa.INTEGER(), nullable=False)
    op.alter_column('attendance', 'sitting_id', existing_type=sa.INTEGER(), nullable=False)


def downgrade() -> None:
    op.alter_column('attendance', 'sitting_id', existing_type=sa.INTEGER(), nullable=True)
    op.alter_column('speech', 'report_id', existing_type=sa.INTEGER(), nullable=True)
    op.alter_column('sitting', 'sitting_date', existing_type=sa.VARCHAR(), nullable=True)
