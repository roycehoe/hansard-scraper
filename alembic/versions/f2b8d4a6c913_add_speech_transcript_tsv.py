"""add a stored tsvector of the speech transcript

Revision ID: f2b8d4a6c913
Revises: 7c1d4e9a2b60
Create Date: 2026-10-14 23:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f2b8d4a6c913'
down_revision: Union[str, Sequence[str], None] = '7c1d4e9a2b60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = 'ix_speech_transcript_tsv'
_LOCK_TIMEOUT = '10s'
_REWRITE_STATEMENT_TIMEOUT = '30min'


def _drop_invalid_index(name: str) -> bool:
    if op.get_context().as_sql:
        return False

    statement = sa.text(
        'SELECT indisvalid FROM pg_index WHERE indexrelid = to_regclass(:name)'
    )
    is_valid = op.get_bind().execute(statement, {'name': name}).scalar()
    if is_valid is not False:
        return False

    op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {name}')
    return True


def upgrade() -> None:
    # NOTE: adding a stored generated column rewrites speech under an ACCESS EXCLUSIVE lock held until this commit
    op.execute(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'")
    op.execute(f"SET LOCAL statement_timeout = '{_REWRITE_STATEMENT_TIMEOUT}'")
    op.execute(
        'ALTER TABLE speech ADD COLUMN IF NOT EXISTS transcript_tsv tsvector '
        "GENERATED ALWAYS AS (to_tsvector('english'::regconfig, transcript)) STORED"
    )

    # NOTE: a concurrent build cannot run inside a transaction, and a failed one leaves an INVALID index behind
    with op.get_context().autocommit_block():
        if _drop_invalid_index(_INDEX_NAME):
            raise RuntimeError(f'Dropped the invalid leftover index {_INDEX_NAME}; rerun the migration')

        try:
            op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX_NAME} ON speech USING gin (transcript_tsv)')
        except sa.exc.DBAPIError:
            _drop_invalid_index(_INDEX_NAME)
            raise

        if _drop_invalid_index(_INDEX_NAME):
            raise RuntimeError(f'Index {_INDEX_NAME} built invalid and was dropped')


def downgrade() -> None:
    op.execute(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'")
    op.execute('ALTER TABLE speech DROP COLUMN IF EXISTS transcript_tsv')
