"""initial schema

Revision ID: 7d4aee897a69
Revises:
Create Date: 2026-06-01 16:14:55.329858

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '7d4aee897a69'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('handsardsittingdateresult')
    for col in ('parlement_no', 'session_no', 'volume_no', 'sitting_no'):
        op.alter_column(
            'handsardsittingdateresponse', col,
            existing_type=sa.VARCHAR(),
            type_=sa.Integer(),
            existing_nullable=True,
            postgresql_using=f"NULLIF({col}, '')::integer",
        )
    op.add_column('parsingstatistics',
                  sa.Column('report_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('parsingstatistics', 'report_id')
    for col in ('sitting_no', 'volume_no', 'session_no', 'parlement_no'):
        op.alter_column(
            'handsardsittingdateresponse', col,
            existing_type=sa.Integer(),
            type_=sa.VARCHAR(),
            existing_nullable=True,
        )
    op.create_table('handsardsittingdateresult',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('member_id', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('volume_no', sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column('report_type', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('session_no', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('portfolio', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('member_name', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('report_version', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('report_start_col', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('sitting_no', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('report_end_col', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('title', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('column_start', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('parl_no', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('report_content', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('column_end', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('report_id', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('score', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('max_result', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('sno', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('full_content_flag', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('from_month', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('from_day', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('from_year', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('html_full_content', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('html_content', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('subtitle', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('sitting_date', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('content', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('mp_names', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('html_file_name', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('ver_pdf', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('foot_notes', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('foot_note_question', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('foot_note_questions', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('foot_note', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('atbp_list', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('ptba_list', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('attendance_list', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('online_pdf_file_name', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('pdf_nodes', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('clarification_text', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('clarification_title', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('clarification_sub_title', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('ptba_from', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('ptba_to', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.Column('question_count', sa.VARCHAR(), autoincrement=False, nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('handsardsittingdateresult_pkey'))
    )
