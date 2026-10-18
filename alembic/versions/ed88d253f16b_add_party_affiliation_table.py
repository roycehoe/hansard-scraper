"""add party affiliation table

Revision ID: ed88d253f16b
Revises: 50505c58da5d
Create Date: 2026-10-18 08:47:57.869733

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ed88d253f16b'
down_revision: Union[str, Sequence[str], None] = '50505c58da5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DATE_PRECISION_NAMES = ('DAY', 'MONTH')


def upgrade() -> None:
    postgresql.ENUM(*_DATE_PRECISION_NAMES, name='dateprecision').create(op.get_bind())
    op.create_table(
        'partyaffiliation',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('party', sa.Text(), nullable=False),
        sa.Column('started_on', sa.Date(), nullable=False),
        sa.Column(
            'started_on_precision',
            postgresql.ENUM(*_DATE_PRECISION_NAMES, name='dateprecision', create_type=False),
            nullable=False,
        ),
        sa.Column('event', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('is_started_on_upper_bound', sa.Boolean(), nullable=False),
        sa.Column('source_report_id', sa.Integer(), nullable=True),
        sa.Column('speaker_id', sa.Integer(), nullable=False),
        sa.CheckConstraint('num_nonnulls(source_url, source_report_id) = 1', name='ck_partyaffiliation_exactly_one_source'),
        sa.ForeignKeyConstraint(['source_report_id'], ['report.id']),
        sa.ForeignKeyConstraint(['speaker_id'], ['speaker.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_partyaffiliation_source_report_id', 'partyaffiliation', ['source_report_id'])
    op.create_index('ix_partyaffiliation_speaker_id', 'partyaffiliation', ['speaker_id'])


def downgrade() -> None:
    op.drop_index('ix_partyaffiliation_speaker_id', table_name='partyaffiliation')
    op.drop_index('ix_partyaffiliation_source_report_id', table_name='partyaffiliation')
    op.drop_table('partyaffiliation')
    postgresql.ENUM(name='dateprecision').drop(op.get_bind())
