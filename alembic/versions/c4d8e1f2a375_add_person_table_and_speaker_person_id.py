"""add person table, speaker.person_id and speaker.is_member

Revision ID: c4d8e1f2a375
Revises: b3f7c2a91d04
Create Date: 2026-10-13 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4d8e1f2a375'
down_revision: Union[str, Sequence[str], None] = 'b3f7c2a91d04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'person',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('canonical_name', sa.Text(), nullable=False),
        sa.Column('basis', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.add_column('speaker', sa.Column('person_id', sa.Integer(), nullable=True))
    op.create_foreign_key('speaker_person_id_fkey', 'speaker', 'person', ['person_id'], ['id'])
    op.create_index('ix_speaker_person_id', 'speaker', ['person_id'])
    # Heads of state (Governors, the Yang di-Pertuan Negara, Presidents) get speaker rows so their
    # speeches can be linked; is_member = false marks them as not members of the House.
    op.add_column('speaker', sa.Column('is_member', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column('speaker', 'is_member')
    op.drop_index('ix_speaker_person_id', table_name='speaker')
    op.drop_constraint('speaker_person_id_fkey', 'speaker', type_='foreignkey')
    op.drop_column('speaker', 'person_id')
    op.drop_table('person')
