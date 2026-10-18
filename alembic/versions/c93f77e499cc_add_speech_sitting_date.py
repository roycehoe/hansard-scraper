"""add the report's sitting date to each speech row, by copying speech

Revision ID: c93f77e499cc
Revises: ed88d253f16b
Create Date: 2026-10-18 12:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c93f77e499cc'
down_revision: Union[str, Sequence[str], None] = 'ed88d253f16b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LOCK_TIMEOUT = '10s'
_COPY_STATEMENT_TIMEOUT = '30min'
_ADDON_INDEX_NAME = 'ix_speech_transcript_tsv_sitting_date_rum'
_ADDED_SHAPE_PREFIXES = (
    'column sitting_date timestamp without time zone true',
    f'index CREATE INDEX {_ADDON_INDEX_NAME} ',
)
_COPY_INDEX_NAME_TO_INDEX_NAME = {
    'speech_new_pkey': 'speech_pkey',
    'ix_speech_new_report_id': 'ix_speech_report_id',
    'ix_speech_new_speaker_id': 'ix_speech_speaker_id',
    'ix_speech_new_transcript_tsv_rum': 'ix_speech_transcript_tsv_rum',
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
# NOTE: each side is summed as row hashes rather than joined or sorted, because under work_mem 2MB a full join of the two tables spilled 2.3 GB of temporary files and a sorted hash 0.8 GB
_ROWS_CHECKSUM = """
    SELECT count(*), sum(('x' || left(row_hash, 16))::bit(64)::bigint::numeric),
        sum(('x' || right(row_hash, 16))::bit(64)::bigint::numeric)
    FROM ({rows}) AS row_hashes
"""
_SPEECH_ROWS_CHECKSUM = sa.text(
    _ROWS_CHECKSUM.format(
        rows='SELECT md5(ROW(speech.id, speech.ordinal, speech.speaker, speech.transcript, speech.report_id, speech.speaker_id, '
        'speech.kind, speech.transcript_tsv, report.sitting_date)::text) AS row_hash '
        'FROM speech LEFT JOIN report ON report.id = speech.report_id'
    )
)
_SPEECH_COPY_ROWS_CHECKSUM = sa.text(
    _ROWS_CHECKSUM.format(
        rows='SELECT md5(ROW(id, ordinal, speaker, transcript, report_id, speaker_id, kind, transcript_tsv, sitting_date)::text) '
        'AS row_hash FROM speech_new'
    )
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


def _validate_swapped_shape(shape_before: set[str]) -> None:
    shape_after = _get_speech_shape()
    lost = shape_before - shape_after
    if lost:
        raise RuntimeError(f'The copy lost {sorted(lost)}')
    added = sorted(shape_after - shape_before)
    if len(added) != len(_ADDED_SHAPE_PREFIXES):
        raise RuntimeError(f'The copy added {added}')
    for line, prefix in zip(added, _ADDED_SHAPE_PREFIXES):
        if not line.startswith(prefix):
            raise RuntimeError(f'The copy added {added}')


def upgrade() -> None:
    if op.get_context().as_sql:
        raise RuntimeError('This migration checks the copy of speech it builds, so it runs online only')

    # NOTE: speech is copied rather than updated in place, because an UPDATE of every row writes each row's words into the text indexes again (about 14 GB of WAL against 1.5 GB for the copy)
    op.execute(f"SET LOCAL lock_timeout = '{_LOCK_TIMEOUT}'")
    op.execute(f"SET LOCAL statement_timeout = '{_COPY_STATEMENT_TIMEOUT}'")
    op.execute('LOCK TABLE speech IN SHARE MODE')
    shape_before = _get_speech_shape()

    op.execute('CREATE TABLE speech_new (LIKE speech INCLUDING ALL EXCLUDING INDEXES)')
    op.execute('ALTER TABLE speech_new ADD COLUMN sitting_date timestamp without time zone NOT NULL')
    op.execute(
        'INSERT INTO speech_new (id, ordinal, speaker, transcript, report_id, speaker_id, kind, sitting_date) '
        'SELECT speech.id, speech.ordinal, speech.speaker, speech.transcript, speech.report_id, speech.speaker_id, '
        'speech.kind, report.sitting_date FROM speech LEFT JOIN report ON report.id = speech.report_id'
    )
    op.execute('ALTER TABLE speech_new ADD CONSTRAINT speech_new_pkey PRIMARY KEY (id)')
    op.execute('CREATE INDEX ix_speech_new_report_id ON speech_new (report_id)')
    op.execute('CREATE INDEX ix_speech_new_speaker_id ON speech_new (speaker_id)')
    op.execute('CREATE INDEX ix_speech_new_transcript_tsv_rum ON speech_new USING rum (transcript_tsv rum_tsvector_ops)')
    op.execute('CREATE INDEX ix_speech_new_transcript_tsv ON speech_new USING gin (transcript_tsv)')
    op.execute(
        'CREATE INDEX ix_speech_new_transcript_tsv_sitting_date_rum ON speech_new '
        "USING rum (transcript_tsv rum_tsvector_addon_ops, sitting_date) WITH (attach = 'sitting_date', to = 'transcript_tsv')"
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
    op.execute(f'DROP INDEX {_ADDON_INDEX_NAME}')
    op.execute('ALTER TABLE speech DROP COLUMN sitting_date')
