"""index report types with their report ids

Revision ID: 91e844f48a2d
Revises: 3733d52d31dc
Create Date: 2026-10-30 12:10:00.000000

"""
from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = '91e844f48a2d'
down_revision: Optional[Union[str, Sequence[str]]] = '3733d52d31dc'
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_INDEX_NAME = 'ix_report_report_type_id'
_INDEX_TARGET = 'report (report_type, id)'


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
        if _drop_invalid_index(_INDEX_NAME):
            raise RuntimeError(f'Dropped the invalid leftover index {_INDEX_NAME}; rerun the migration')

        try:
            op.execute(f'CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX_NAME} ON {_INDEX_TARGET}')
        except sa.exc.DBAPIError:
            _drop_invalid_index(_INDEX_NAME)
            raise

        if _drop_invalid_index(_INDEX_NAME):
            raise RuntimeError(f'Index {_INDEX_NAME} built invalid and was dropped')


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS {_INDEX_NAME}')
