"""cover the seat browse with the speaker index

Revision ID: 3733d52d31dc
Revises: 84f98b2550da
Create Date: 2026-10-30 12:00:00.000000

"""
from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = '3733d52d31dc'
down_revision: Optional[Union[str, Sequence[str]]] = '84f98b2550da'
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_INDEX_NAME = 'ix_speech_speaker_id'
_NEW_INDEX_NAME = 'ix_speech_speaker_id_new'
_COVERING_TARGET = 'speech (speaker_id, sitting_date, id) INCLUDE (report_id, speaker)'
_PREVIOUS_TARGET = 'speech (speaker_id) INCLUDE (report_id)'


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


def _create_index(name: str, target: str) -> None:
    if _drop_invalid_index(name):
        raise RuntimeError(f'Dropped the invalid leftover index {name}; rerun the migration')

    try:
        op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {target}')
    except sa.exc.DBAPIError:
        _drop_invalid_index(name)
        raise

    if _drop_invalid_index(name):
        raise RuntimeError(f'Index {name} built invalid and was dropped')


def _replace_index(target: str) -> None:
    # NOTE: the new index is built beside the old one and renamed, so speaker_id lookups never run without an index
    _create_index(_NEW_INDEX_NAME, target)
    op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_NAME}')
    op.execute(f'ALTER INDEX {_NEW_INDEX_NAME} RENAME TO {_INDEX_NAME}')


def upgrade() -> None:
    # NOTE: a concurrent build cannot run inside a transaction, and a failed one leaves an INVALID index behind
    with op.get_context().autocommit_block():
        _replace_index(_COVERING_TARGET)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        _replace_index(_PREVIOUS_TARGET)
