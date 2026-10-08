"""rename handsard tables to hansard

Revision ID: a7c1d4e9b206
Revises: e3a2f1b8c904
Create Date: 2026-10-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c1d4e9b206'
down_revision: Union[str, Sequence[str], None] = 'e3a2f1b8c904'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Postgres does not rename the primary-key constraint (and its index) or the
# id sequence when a table is renamed, so each is renamed explicitly.
_TABLES = ('sittingdateresponse', 'websiteresponse')


def _rename(old_prefix: str, new_prefix: str) -> None:
    for suffix in _TABLES:
        old, new = f'{old_prefix}{suffix}', f'{new_prefix}{suffix}'
        # IF EXISTS: handsardwebsiteresponse is not created by any migration
        # in alembic/versions/, so it may be absent on some databases.
        op.execute(f'ALTER TABLE IF EXISTS {old} RENAME TO {new}')
        op.execute(f'ALTER TABLE IF EXISTS {new} RENAME CONSTRAINT {old}_pkey TO {new}_pkey')
        op.execute(f'ALTER SEQUENCE IF EXISTS {old}_id_seq RENAME TO {new}_id_seq')


def upgrade() -> None:
    _rename('handsard', 'hansard')


def downgrade() -> None:
    _rename('hansard', 'handsard')
