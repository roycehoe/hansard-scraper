"""rename mp_names to speaker_names

Revision ID: e3a2f1b8c904
Revises: d11de512cd70
Create Date: 2026-06-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e3a2f1b8c904'
down_revision: Union[str, Sequence[str], None] = 'd11de512cd70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('handsardsittingdateresponse', 'mp_names', new_column_name='speaker_names')
    op.alter_column('sitting', 'mp_names', new_column_name='speaker_names')


def downgrade() -> None:
    op.alter_column('sitting', 'speaker_names', new_column_name='mp_names')
    op.alter_column('handsardsittingdateresponse', 'speaker_names', new_column_name='mp_names')
