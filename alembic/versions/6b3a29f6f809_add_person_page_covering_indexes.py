"""cover the person page reads with include indexes

Revision ID: 6b3a29f6f809
Revises: 8281c763bb21
Create Date: 2026-10-21 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6b3a29f6f809'
down_revision: Union[str, Sequence[str], None] = '8281c763bb21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COVERING_INDEXES = (
    ('ix_speech_speaker_id', 'speech (speaker_id) INCLUDE (report_id)'),
    ('ix_attendance_speaker_id', 'attendance (speaker_id) INCLUDE (is_present, sitting_id, location_name)'),
)
_PLAIN_INDEXES = (
    ('ix_speech_speaker_id', 'speech (speaker_id)'),
    ('ix_attendance_speaker_id', 'attendance (speaker_id)'),
)
_REPORT_INDEX_NAME = 'ix_report_id_parliament_number'
_REPORT_INDEX_TARGET = 'report (id) INCLUDE (parliament_number)'


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


def upgrade() -> None:
    # NOTE: a concurrent build cannot run inside a transaction, and a failed one leaves an INVALID index behind
    with op.get_context().autocommit_block():
        for name, target in _COVERING_INDEXES:
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {name}')
            _create_index(name, target)

        _create_index(_REPORT_INDEX_NAME, _REPORT_INDEX_TARGET)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {_REPORT_INDEX_NAME}')

        for name, target in _PLAIN_INDEXES:
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {name}')
            _create_index(name, target)
