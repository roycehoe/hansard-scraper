"""add column numbers to report and speech

Revision ID: 84f98b2550da
Revises: c5cea5c26a58
Create Date: 2026-10-24 00:40:00.000000

"""
from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = '84f98b2550da'
down_revision: Optional[Union[str, Sequence[str]]] = 'c5cea5c26a58'
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_COLUMN_NOTE_NAMES = (
    'LIKELY_MISPRINT',
    'SPEAKER_NAMED_IN_COLUMN_BEFORE',
    'PRINTED_WITH_L_FOR_1',
)


def upgrade() -> None:
    postgresql.ENUM(*_COLUMN_NOTE_NAMES, name='columnnote').create(op.get_bind())
    op.add_column('report', sa.Column('column_start', sa.Integer(), nullable=True))
    op.add_column('report', sa.Column('column_end', sa.Integer(), nullable=True))
    op.add_column('speech', sa.Column('column_start', sa.Integer(), nullable=True))
    op.add_column(
        'speech',
        sa.Column('column_note', postgresql.ENUM(*_COLUMN_NOTE_NAMES, name='columnnote', create_type=False), nullable=True),
    )
    op.add_column('speech', sa.Column('column_suggested', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('speech', 'column_suggested')
    op.drop_column('speech', 'column_note')
    op.drop_column('speech', 'column_start')
    op.drop_column('report', 'column_end')
    op.drop_column('report', 'column_start')
    postgresql.ENUM(name='columnnote').drop(op.get_bind())
