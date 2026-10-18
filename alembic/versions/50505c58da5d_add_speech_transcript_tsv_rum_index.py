"""add a rum index on the speech tsvector for relevance order

Revision ID: 50505c58da5d
Revises: 641870b78b3f
Create Date: 2026-10-18 07:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '50505c58da5d'
down_revision: Union[str, Sequence[str], None] = '641870b78b3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX_NAME = 'ix_speech_transcript_tsv_rum'


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
    op.execute('CREATE EXTENSION IF NOT EXISTS rum')

    # NOTE: a concurrent build cannot run inside a transaction, and a failed one leaves an INVALID index behind
    with op.get_context().autocommit_block():
        if _drop_invalid_index(_INDEX_NAME):
            raise RuntimeError(f'Dropped the invalid leftover index {_INDEX_NAME}; rerun the migration')

        try:
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX_NAME} ON speech USING rum (transcript_tsv rum_tsvector_ops)'
            )
        except sa.exc.DBAPIError:
            _drop_invalid_index(_INDEX_NAME)
            raise

        if _drop_invalid_index(_INDEX_NAME):
            raise RuntimeError(f'Index {_INDEX_NAME} built invalid and was dropped')

    # NOTE: transcript_tsv has had no statistics since it was added, so the planner took any word for a rare one and rescanned this index once per report under a date range
    op.execute('ANALYZE speech')


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_NAME}')
    op.execute('DROP EXTENSION IF EXISTS rum')
