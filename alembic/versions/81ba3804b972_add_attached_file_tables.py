"""add attached file tables

Revision ID: 81ba3804b972
Revises: e1a5c7b9d3f2
Create Date: 2026-11-09 09:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "81ba3804b972"
down_revision: Optional[Union[str, Sequence[str]]] = "e1a5c7b9d3f2"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_ATTACHED_FILE_KIND_NAMES = ("ANNEX", "VERNACULAR")
_POINTER_SHAPE_NAMES = ("DATED", "PDFS", "SECTION_FILE")
_PARAGRAPH_TIE_RULE_NAMES = (
    "ONLY_OCCURRENCE",
    "EVERY_OCCURRENCE_A_LINK",
    "OCCURRENCE_BESIDE_PLAIN_TEXT",
)


def upgrade() -> None:
    postgresql.ENUM(*_ATTACHED_FILE_KIND_NAMES, name="attachedfilekind").create(
        op.get_bind()
    )
    postgresql.ENUM(*_POINTER_SHAPE_NAMES, name="attachedfilepointershape").create(
        op.get_bind()
    )
    postgresql.ENUM(*_PARAGRAPH_TIE_RULE_NAMES, name="paragraphtierule").create(
        op.get_bind()
    )
    op.create_table(
        "attached_file",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                *_ATTACHED_FILE_KIND_NAMES, name="attachedfilekind", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("sprs_file_id", sa.Integer(), nullable=False),
        sa.Column("printed_title", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "printed_file_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("file_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("section_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("download_value", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("sitting_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["sitting_id"], ["sitting.id"], name="attached_file_sitting_id_fkey"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sitting_id",
            "kind",
            "sprs_file_id",
            name="uq_attached_file_sitting_id_kind_sprs_file_id",
        ),
    )
    op.create_index("ix_attached_file_sitting_id", "attached_file", ["sitting_id"])
    op.create_table(
        "attached_file_pointer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("printed_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("href", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "shape",
            postgresql.ENUM(
                *_POINTER_SHAPE_NAMES,
                name="attachedfilepointershape",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("download_value", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("speech_ordinal", sa.Integer(), nullable=True),
        sa.Column(
            "paragraph_tie_rule",
            postgresql.ENUM(
                *_PARAGRAPH_TIE_RULE_NAMES, name="paragraphtierule", create_type=False
            ),
            nullable=True,
        ),
        sa.Column("sprs_report_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("attached_file_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["sprs_report_id"],
            ["report.report_id"],
            name="attached_file_pointer_sprs_report_id_fkey",
        ),
        sa.ForeignKeyConstraint(
            ["attached_file_id"],
            ["attached_file.id"],
            name="attached_file_pointer_attached_file_id_fkey",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sprs_report_id",
            "ordinal",
            name="uq_attached_file_pointer_sprs_report_id_ordinal",
        ),
    )
    op.create_index(
        "ix_attached_file_pointer_sprs_report_id",
        "attached_file_pointer",
        ["sprs_report_id"],
    )
    op.create_index(
        "ix_attached_file_pointer_attached_file_id",
        "attached_file_pointer",
        ["attached_file_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_attached_file_pointer_attached_file_id", table_name="attached_file_pointer"
    )
    op.drop_index(
        "ix_attached_file_pointer_sprs_report_id", table_name="attached_file_pointer"
    )
    op.drop_table("attached_file_pointer")
    op.drop_index("ix_attached_file_sitting_id", table_name="attached_file")
    op.drop_table("attached_file")
    postgresql.ENUM(name="paragraphtierule").drop(op.get_bind())
    postgresql.ENUM(name="attachedfilepointershape").drop(op.get_bind())
    postgresql.ENUM(name="attachedfilekind").drop(op.get_bind())
