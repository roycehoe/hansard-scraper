"""add the report's type to each speech row and both rum indexes, by copying speech

Revision ID: 82478ba59541
Revises: b8447a11fda2
Create Date: 2026-10-30 12:40:00.000000

"""
from typing import Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = '82478ba59541'
down_revision: Optional[Union[str, Sequence[str]]] = 'b8447a11fda2'
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_LOCK_TIMEOUT = '10s'
_COPY_STATEMENT_TIMEOUT = '30min'
_RUM_INDEX_NAME = 'ix_speech_transcript_tsv_rum'
_ADDON_INDEX_NAME = 'ix_speech_transcript_tsv_sitting_date_rum'
_CHANGED_INDEX_PREFIXES = (
    f'index CREATE INDEX {_RUM_INDEX_NAME} ',
    f'index CREATE INDEX {_ADDON_INDEX_NAME} ',
)
_ADDED_SHAPE_PREFIXES = ('column report_type character varying true', *_CHANGED_INDEX_PREFIXES)
_COPY_INDEX_NAME_TO_INDEX_NAME = {
    'speech_new_pkey': 'speech_pkey',
    'ix_speech_new_report_id': 'ix_speech_report_id',
    'ix_speech_new_speaker_id': 'ix_speech_speaker_id',
    'ix_speech_new_transcript_tsv_rum': _RUM_INDEX_NAME,
    'ix_speech_new_transcript_tsv': 'ix_speech_transcript_tsv',
    'ix_speech_new_transcript_tsv_sitting_date_rum': _ADDON_INDEX_NAME,
    'ix_speech_new_transcript_fts': 'ix_speech_transcript_fts',
}
_COPY_CONSTRAINT_NAME_TO_CONSTRAINT_NAME = {
    'speech_new_report_id_fkey': 'speech_report_id_fkey',
    'speech_new_speaker_id_fkey': 'speech_speaker_id_fkey',
}
_SPEECH_SHAPE = sa.text(
    """
    SELECT 'owner ' || pg_get_userbyid(relowner) || ' ' || relpersistence::text || ' ' || relreplident::text || ' '
        || relrowsecurity || ' ' || coalesce(array_to_string(reloptions, ','), '')
    FROM pg_class WHERE oid = 'speech'::regclass
    UNION ALL
    SELECT 'privilege ' || CASE WHEN acl.grantee = 0 THEN 'PUBLIC' ELSE pg_get_userbyid(acl.grantee) END
        || ' ' || acl.privilege_type || ' ' || acl.is_grantable
    FROM pg_class, aclexplode(coalesce(relacl, acldefault('r', relowner))) AS acl
    WHERE pg_class.oid = 'speech'::regclass
    UNION ALL
    SELECT 'column ' || attname || ' ' || format_type(atttypid, atttypmod) || ' ' || attnotnull || ' '
        || attgenerated::text || ' ' || attidentity::text || ' ' || coalesce(pg_get_expr(adbin, adrelid), '')
    FROM pg_attribute LEFT JOIN pg_attrdef ON adrelid = attrelid AND adnum = attnum
    WHERE attrelid = 'speech'::regclass AND attnum > 0 AND NOT attisdropped
    UNION ALL
    SELECT 'index ' || pg_get_indexdef(indexrelid) FROM pg_index WHERE indrelid = 'speech'::regclass
    UNION ALL
    SELECT 'constraint ' || conname || ' ' || pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = 'speech'::regclass
    UNION ALL
    SELECT 'trigger ' || pg_get_triggerdef(oid) FROM pg_trigger WHERE tgrelid = 'speech'::regclass AND NOT tgisinternal
    UNION ALL
    SELECT 'policy ' || polname FROM pg_policy WHERE polrelid = 'speech'::regclass
    UNION ALL
    SELECT 'publication ' || pubname FROM pg_publication_tables WHERE schemaname = 'public' AND tablename = 'speech'
    UNION ALL
    SELECT 'sequence ' || pg_get_serial_sequence('speech', 'id')
    """
)
_COPY_GRANTS = sa.text(
    """
    SELECT CASE WHEN acl.grantee = 0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(acl.grantee)) END,
        acl.privilege_type, acl.is_grantable
    FROM pg_class, aclexplode(relacl) AS acl
    WHERE pg_class.oid = 'speech'::regclass AND acl.grantee <> pg_class.relowner
    """
)
_COPIED_COLUMNS = (
    'id', 'ordinal', 'speaker', 'transcript', 'report_id', 'speaker_id', 'kind', 'sitting_date', 'column_start', 'column_note', 'column_suggested',
)
_COPY_COLUMN_LIST = ', '.join(_COPIED_COLUMNS)
_SPEECH_COLUMN_LIST = ', '.join(f'speech.{column}' for column in _COPIED_COLUMNS)
# NOTE: each side is summed as row hashes rather than joined or sorted, because under work_mem 2MB a full join of the two tables spilled 2.3 GB of temporary files and a sorted hash 0.8 GB
_ROWS_CHECKSUM = """
    SELECT count(*), sum(('x' || left(row_hash, 16))::bit(64)::bigint::numeric),
        sum(('x' || right(row_hash, 16))::bit(64)::bigint::numeric)
    FROM ({rows}) AS row_hashes
"""
_SPEECH_ROWS_CHECKSUM = sa.text(
    _ROWS_CHECKSUM.format(
        rows=f'SELECT md5(ROW({_SPEECH_COLUMN_LIST}, speech.transcript_tsv, report.report_type)::text) AS row_hash '
        'FROM speech LEFT JOIN report ON report.id = speech.report_id'
    )
)
_SPEECH_COPY_ROWS_CHECKSUM = sa.text(
    _ROWS_CHECKSUM.format(rows=f'SELECT md5(ROW({_COPY_COLUMN_LIST}, transcript_tsv, report_type)::text) AS row_hash FROM speech_new')
)


def _get_speech_shape() -> set[str]:
    return set(op.get_bind().execute(_SPEECH_SHAPE).scalars())


def _copy_grants() -> None:
    for grantee, privilege, is_grantable in op.get_bind().execute(_COPY_GRANTS).all():
        grant_option = ' WITH GRANT OPTION' if is_grantable else ''
        op.execute(f'GRANT {privilege} ON speech_new TO {grantee}{grant_option}')


def _validate_copy() -> None:
    rows_checksum = tuple(op.get_bind().execute(_SPEECH_ROWS_CHECKSUM).one())
    copy_rows_checksum = tuple(op.get_bind().execute(_SPEECH_COPY_ROWS_CHECKSUM).one())
    if rows_checksum != copy_rows_checksum:
        raise RuntimeError(f'speech {rows_checksum} and its copy {copy_rows_checksum} differ')


def _validate_lines(lines: set[str], prefixes: tuple[str, ...], change: str) -> None:
    sorted_lines = sorted(lines)
    if len(sorted_lines) != len(prefixes) or not all(line.startswith(prefix) for line, prefix in zip(sorted_lines, prefixes)):
        raise RuntimeError(f'The copy {change} {sorted_lines}')


def _validate_swapped_shape(shape_before: set[str]) -> None:
    shape_after = _get_speech_shape()
    # NOTE: the two rum indexes keep their names and gain report_type, so each shows as one line lost and one added
    _validate_lines(shape_before - shape_after, _CHANGED_INDEX_PREFIXES, 'lost')
    _validate_lines(shape_after - shape_before, _ADDED_SHAPE_PREFIXES, 'added')


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError('This migration checks the copy of speech it builds, so it runs online only')

    # NOTE: speech is copied rather than updated in place, because an UPDATE of every row writes each row's words into the text indexes again (about 14 GB of WAL against 1.5 GB for the copy)
    op.execute(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'")
    op.execute(f"SET LOCAL statement_timeout = '{_COPY_STATEMENT_TIMEOUT}'")
    op.execute('LOCK TABLE speech IN SHARE MODE')
    shape_before = _get_speech_shape()

    op.execute('CREATE TABLE speech_new (LIKE speech INCLUDING ALL EXCLUDING INDEXES)')
    op.execute('ALTER TABLE speech_new ADD COLUMN report_type character varying NOT NULL')
    op.execute(
        f'INSERT INTO speech_new ({_COPY_COLUMN_LIST}, report_type) '
        f'SELECT {_SPEECH_COLUMN_LIST}, report.report_type FROM speech LEFT JOIN report ON report.id = speech.report_id'
    )
    op.execute('ALTER TABLE speech_new ADD CONSTRAINT speech_new_pkey PRIMARY KEY (id)')
    op.execute('CREATE INDEX ix_speech_new_report_id ON speech_new (report_id)')
    op.execute('CREATE INDEX ix_speech_new_speaker_id ON speech_new (speaker_id, sitting_date, id) INCLUDE (report_id, speaker)')
    op.execute(
        'CREATE INDEX ix_speech_new_transcript_tsv_rum ON speech_new '
        'USING rum (transcript_tsv rum_tsvector_ops, report_type rum_varchar_ops)'
    )
    op.execute('CREATE INDEX ix_speech_new_transcript_tsv ON speech_new USING gin (transcript_tsv)')
    # NOTE: report_type comes before the attached sitting_date, so a type filter narrows the matches the index returns in date order
    op.execute(
        'CREATE INDEX ix_speech_new_transcript_tsv_sitting_date_rum ON speech_new '
        'USING rum (transcript_tsv rum_tsvector_addon_ops, report_type rum_varchar_ops, sitting_date) '
        "WITH (attach = 'sitting_date', to = 'transcript_tsv')"
    )
    op.execute(
        "CREATE INDEX ix_speech_new_transcript_fts ON speech_new USING gin (to_tsvector('english'::regconfig, transcript))"
    )
    op.execute('ALTER TABLE speech_new ADD CONSTRAINT speech_new_report_id_fkey FOREIGN KEY (report_id) REFERENCES report (id)')
    op.execute('ALTER TABLE speech_new ADD CONSTRAINT speech_new_speaker_id_fkey FOREIGN KEY (speaker_id) REFERENCES speaker (id)')
    _copy_grants()
    _validate_copy()
    # NOTE: analysed before the swap, because the statistics follow the table through the rename and readers wait while the swap holds its lock
    op.execute('ANALYZE speech_new')

    op.execute('LOCK TABLE speech IN ACCESS EXCLUSIVE MODE')
    # NOTE: the sequence moves first, because dropping speech would drop the sequence it owns
    op.execute('ALTER SEQUENCE speech_id_seq OWNED BY speech_new.id')
    op.execute('DROP TABLE speech')
    op.execute('ALTER TABLE speech_new RENAME TO speech')
    for copy_index_name, index_name in _COPY_INDEX_NAME_TO_INDEX_NAME.items():
        op.execute(f'ALTER INDEX {copy_index_name} RENAME TO {index_name}')
    for copy_constraint_name, constraint_name in _COPY_CONSTRAINT_NAME_TO_CONSTRAINT_NAME.items():
        op.execute(f'ALTER TABLE speech RENAME CONSTRAINT {copy_constraint_name} TO {constraint_name}')
    _validate_swapped_shape(shape_before)


def downgrade() -> None:
    op.execute(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'")
    op.execute(f"SET LOCAL statement_timeout = '{_COPY_STATEMENT_TIMEOUT}'")
    # NOTE: dropping the column drops both rum indexes, which are then built again without it
    op.execute('ALTER TABLE speech DROP COLUMN report_type')
    op.execute(f'CREATE INDEX {_RUM_INDEX_NAME} ON speech USING rum (transcript_tsv rum_tsvector_ops)')
    op.execute(
        f'CREATE INDEX {_ADDON_INDEX_NAME} ON speech '
        "USING rum (transcript_tsv rum_tsvector_addon_ops, sitting_date) WITH (attach = 'sitting_date', to = 'transcript_tsv')"
    )
