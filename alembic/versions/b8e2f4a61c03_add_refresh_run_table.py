"""add refresh_run table

Revision ID: b8e2f4a61c03
Revises: c93f77e499cc
Create Date: 2026-10-18 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'b8e2f4a61c03'
down_revision: Union[str, Sequence[str], None] = 'c93f77e499cc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COUNT_COLUMNS = (
    'website_responses_added', 'sitting_date_responses_added', 'sittings_added', 'reports_added',
    'speeches_added', 'speeches_linked', 'speeches_named_unlinked', 'attendances_added', 'attendances_linked',
    'reports_held_without_text', 'reports_without_speech_rows', 'reports_rechecked', 'reports_changed',
)


def upgrade() -> None:
    op.create_table(
        'refresh_run',
        sa.Column('id', sa.Integer(), nullable=False),
        *(sa.Column(name, sa.Integer(), nullable=False) for name in _COUNT_COLUMNS),
        sa.Column('latest_sitting_date_with_text', sa.Date(), nullable=True),
        sa.Column('figures', postgresql.JSONB(), nullable=True),
        sa.Column('halt_reason', sa.Text(), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.CheckConstraint("status IN ('RUNNING', 'SUCCEEDED', 'HALTED', 'FAILED')", name='ck_refresh_run_status'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_refresh_run_started_at', 'refresh_run', ['started_at'])


def downgrade() -> None:
    op.drop_index('ix_refresh_run_started_at', table_name='refresh_run')
    op.drop_table('refresh_run')
