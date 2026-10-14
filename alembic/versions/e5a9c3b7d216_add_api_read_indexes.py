"""add the indexes the read API relies on

Revision ID: e5a9c3b7d216
Revises: c4d8e1f2a375
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5a9c3b7d216'
down_revision: Union[str, Sequence[str], None] = 'c4d8e1f2a375'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = (
    ('ix_speech_report_id', 'speech (report_id)'),
    ('ix_speech_speaker_id', 'speech (speaker_id)'),
    ('ix_attendance_sitting_id', 'attendance (sitting_id)'),
    ('ix_attendance_speaker_id', 'attendance (speaker_id)'),
    ('ix_report_sitting_date_parliament_number', 'report (sitting_date, parliament_number)'),
    ('ix_report_title_fts', "report USING gin (to_tsvector('english', title))"),
    ('ix_speech_transcript_fts', "speech USING gin (to_tsvector('english', transcript))"),
)


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
    # NOTE: a concurrent build cannot run inside a transaction, and a failed one leaves an INVALID index behind
    with op.get_context().autocommit_block():
        for name, target in _INDEXES:
            if _drop_invalid_index(name):
                raise RuntimeError(f'Dropped the invalid leftover index {name}; rerun the migration')

            try:
                op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {target}')
            except sa.exc.DBAPIError:
                _drop_invalid_index(name)
                raise

            if _drop_invalid_index(name):
                raise RuntimeError(f'Index {name} built invalid and was dropped')


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _ in reversed(_INDEXES):
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {name}')
