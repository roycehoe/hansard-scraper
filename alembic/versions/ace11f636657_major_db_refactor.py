"""major db refactor

Revision ID: ace11f636657
Revises: 7d4aee897a69
Create Date: 2026-06-01 16:57:39.039859

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'ace11f636657'
down_revision: Union[str, Sequence[str], None] = '7d4aee897a69'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Add JSON columns to sitting ───────────────────────────────────────
    op.add_column('sitting', sa.Column('sections', sa.Text(), nullable=True))
    op.add_column('sitting', sa.Column('annexures', sa.Text(), nullable=True))
    op.add_column('sitting', sa.Column('vernaculars', sa.Text(), nullable=True))
    op.add_column('sitting', sa.Column('a2b', sa.Text(), nullable=True))

    # ── 2. Migrate child table rows into sitting JSON columns ─────────────────
    # Child tables FK to handsardsittingdateresponse.id; sitting is correlated
    # to handsardsittingdateresponse via sitting_date (1:1 relationship).
    for col, child_table in [
        ('sections',   'sittingsection'),
        ('annexures',  'sittingannexure'),
        ('vernaculars', 'sittingvernacular'),
        ('a2b',        'sittinga2b'),
    ]:
        conn.execute(text(f"""
            UPDATE sitting s
            SET {col} = sub.data
            FROM (
                SELECT h.sitting_date, json_agg(row_to_json(c))::text AS data
                FROM {child_table} c
                JOIN handsardsittingdateresponse h ON h.id = c.sitting_id
                GROUP BY h.sitting_date
            ) sub
            WHERE s.sitting_date = sub.sitting_date
        """))

    # ── 3. Drop child tables and parsingstatistics ────────────────────────────
    op.drop_table('sittingptba')
    op.drop_table('sittingsection')
    op.drop_table('sittingannexure')
    op.drop_table('sittingvernacular')
    op.drop_table('sittinga2b')
    op.drop_table('parsingstatistics')

    # ── 4. Rename sittingattendance → attendance, mp_id → speaker_id ─────────
    # Drop FK before renaming so constraint names stay consistent.
    op.drop_constraint('sittingattendance_mp_id_fkey', 'sittingattendance', type_='foreignkey')
    op.alter_column('sittingattendance', 'mp_id', new_column_name='speaker_id')
    op.rename_table('sittingattendance', 'attendance')
    # Recreate FK now pointing to mp (will be updated when mp is renamed below)
    op.create_foreign_key('attendance_speaker_id_fkey', 'attendance', 'mp', ['speaker_id'], ['id'])

    # ── 5. Rename mp → speaker ────────────────────────────────────────────────
    op.rename_table('mp', 'speaker')

    # ── 6. Rename speech.mp_id → speaker_id ──────────────────────────────────
    op.drop_constraint('speech_mp_id_fkey', 'speech', type_='foreignkey')
    op.alter_column('speech', 'mp_id', new_column_name='speaker_id')
    op.create_foreign_key('speech_speaker_id_fkey', 'speech', 'speaker', ['speaker_id'], ['id'])


def downgrade() -> None:
    # ── Reverse speech rename ─────────────────────────────────────────────────
    op.drop_constraint('speech_speaker_id_fkey', 'speech', type_='foreignkey')
    op.alter_column('speech', 'speaker_id', new_column_name='mp_id')
    op.create_foreign_key('speech_mp_id_fkey', 'speech', 'mp', ['mp_id'], ['id'])

    # ── Reverse speaker → mp rename ───────────────────────────────────────────
    op.rename_table('speaker', 'mp')

    # ── Reverse attendance rename ─────────────────────────────────────────────
    op.drop_constraint('attendance_speaker_id_fkey', 'attendance', type_='foreignkey')
    op.rename_table('attendance', 'sittingattendance')
    op.alter_column('sittingattendance', 'speaker_id', new_column_name='mp_id')
    op.create_foreign_key('sittingattendance_mp_id_fkey', 'sittingattendance', 'mp', ['mp_id'], ['id'])

    # ── Recreate dropped tables (empty — data is gone) ────────────────────────
    op.create_table('parsingstatistics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('volume_number', sa.Integer(), nullable=False),
        sa.Column('parliament_number', sa.Integer(), nullable=False),
        sa.Column('sitting_number', sa.Integer(), nullable=True),
        sa.Column('sitting_date', sa.DateTime(), nullable=False),
        sa.Column('speech_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('subtitle', sa.Text(), nullable=True),
        sa.Column('has_markdown', sa.Boolean(), nullable=False),
        sa.Column('has_start_line', sa.Boolean(), nullable=False),
        sa.Column('can_get_speeches', sa.Boolean(), nullable=False),
        sa.Column('report_type', sa.Text(), nullable=False),
        sa.Column('report_version', sa.Text(), nullable=False),
        sa.Column('report_id', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('sittingptba',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sitting_id', sa.Integer(), nullable=True),
        sa.Column('mp_name', sa.Text(), nullable=True),
        sa.Column('from_date', sa.Text(), nullable=True),
        sa.Column('to_date', sa.Text(), nullable=True),
        sa.Column('start_dt_text', sa.Text(), nullable=True),
        sa.Column('end_dt_text', sa.Text(), nullable=True),
        sa.Column('start_dt_flag', sa.Boolean(), nullable=True),
        sa.Column('end_dt_flag', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['sitting_id'], ['handsardsittingdateresponse.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('sittingsection',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sitting_id', sa.Integer(), nullable=True),
        sa.Column('start_pg_no', sa.Integer(), nullable=True),
        sa.Column('end_pg_no', sa.Integer(), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('sub_title', sa.Text(), nullable=True),
        sa.Column('section_type', sa.Text(), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('clarification_text', sa.Text(), nullable=True),
        sa.Column('clarification_title', sa.Text(), nullable=True),
        sa.Column('clarification_sub_title', sa.Text(), nullable=True),
        sa.Column('report_type', sa.Text(), nullable=True),
        sa.Column('question_count', sa.Text(), nullable=True),
        sa.Column('foot_notes', sa.Text(), nullable=True),
        sa.Column('foot_note_questions', sa.Text(), nullable=True),
        sa.Column('question_no', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['sitting_id'], ['handsardsittingdateresponse.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('sittingannexure',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sitting_id', sa.Integer(), nullable=True),
        sa.Column('annexure_id', sa.Integer(), nullable=True),
        sa.Column('sitting_date', sa.Text(), nullable=True),
        sa.Column('annexure_title', sa.Text(), nullable=True),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('file_name', sa.Text(), nullable=True),
        sa.Column('section_type', sa.Text(), nullable=True),
        sa.Column('file', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['sitting_id'], ['handsardsittingdateresponse.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('sittingvernacular',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sitting_id', sa.Integer(), nullable=True),
        sa.Column('vernacular_id', sa.Integer(), nullable=True),
        sa.Column('sitting_date', sa.Text(), nullable=True),
        sa.Column('vernacular_title', sa.Text(), nullable=True),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('file_name', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['sitting_id'], ['handsardsittingdateresponse.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table('sittinga2b',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sitting_id', sa.Integer(), nullable=True),
        sa.Column('date', sa.Text(), nullable=True),
        sa.Column('bill', sa.Text(), nullable=True),
        sa.Column('atbp_preview_text', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['sitting_id'], ['handsardsittingdateresponse.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # ── Drop sitting JSON columns ─────────────────────────────────────────────
    op.drop_column('sitting', 'a2b')
    op.drop_column('sitting', 'vernaculars')
    op.drop_column('sitting', 'annexures')
    op.drop_column('sitting', 'sections')
