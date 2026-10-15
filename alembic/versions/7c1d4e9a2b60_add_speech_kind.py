"""add the kind column to speech

Revision ID: 7c1d4e9a2b60
Revises: e5a9c3b7d216
Create Date: 2026-10-15 22:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7c1d4e9a2b60'
down_revision: Union[str, Sequence[str], None] = 'e5a9c3b7d216'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SPEECH_KIND_NAMES = (
    'SPEECH',
    'PROCEDURAL',
    'CHAMBER_EVENT',
    'EDITORIAL_NOTE',
    'DOCUMENT_TEXT',
    'HEADING',
    'UNCLASSIFIED',
)


def upgrade() -> None:
    postgresql.ENUM(*_SPEECH_KIND_NAMES, name='speechkind').create(op.get_bind())
    op.add_column(
        'speech',
        sa.Column('kind', postgresql.ENUM(*_SPEECH_KIND_NAMES, name='speechkind', create_type=False), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('speech', 'kind')
    postgresql.ENUM(name='speechkind').drop(op.get_bind())
