"""add office and ministry tables

Revision ID: e7b4c2a9f1d3
Revises: d9e4f2a7b3c1
Create Date: 2026-11-09 09:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e7b4c2a9f1d3"
down_revision: Optional[Union[str, Sequence[str]]] = "d9e4f2a7b3c1"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_ATTENDANCE_OFFICE_SOURCE_NAMES = (
    "AFTER_CONSTITUENCY_BRACKET",
    "AFTER_NAME_COMMA",
    "CHAIR_FORM",
    "BEFORE_EX_OFFICIO_BRACKET",
)
_REPORT_PUT_TO_SOURCE_NAMES = ("ASKED_THE", "TO_ASK_THE")
_OFFICE_TITLE_MINISTRY_SOURCE_NAMES = ("CLOSED_LIST_RULE", "HAND_KEPT_TITLE")
_OFFICE_CLASS_NAMES = (
    "PRIME_MINISTER",
    "DEPUTY_PRIME_MINISTER",
    "MINISTER",
    "SENIOR_MINISTER_OF_STATE",
    "MINISTER_OF_STATE",
    "SENIOR_PARLIAMENTARY_SECRETARY",
    "PARLIAMENTARY_SECRETARY",
    "OTHER",
)


def upgrade() -> None:
    postgresql.ENUM(
        *_ATTENDANCE_OFFICE_SOURCE_NAMES, name="attendanceofficesource"
    ).create(op.get_bind())
    postgresql.ENUM(*_REPORT_PUT_TO_SOURCE_NAMES, name="reportputtosource").create(
        op.get_bind()
    )
    postgresql.ENUM(
        *_OFFICE_TITLE_MINISTRY_SOURCE_NAMES, name="officetitleministrysource"
    ).create(op.get_bind())
    op.create_table(
        "attendance_office",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("office_printed", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "entry_line_printed", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column(
            "office_class",
            postgresql.ENUM(
                *_OFFICE_CLASS_NAMES, name="officeclass", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "source",
            postgresql.ENUM(
                *_ATTENDANCE_OFFICE_SOURCE_NAMES,
                name="attendanceofficesource",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attendance_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["attendance_id"], ["attendance.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attendance_id", name="uq_attendance_office_attendance_id"),
    )
    op.create_table(
        "office_printed_range",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("office_printed", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "office_class",
            postgresql.ENUM(
                *_OFFICE_CLASS_NAMES, name="officeclass", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("sitting_count", sa.Integer(), nullable=False),
        sa.Column("first_sitting_date", sa.DateTime(), nullable=False),
        sa.Column("last_sitting_date", sa.DateTime(), nullable=False),
        sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=False),
        sa.Column("first_attendance_office_id", sa.Integer(), nullable=False),
        sa.Column("last_attendance_office_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"]),
        sa.ForeignKeyConstraint(
            ["first_attendance_office_id"], ["attendance_office.id"]
        ),
        sa.ForeignKeyConstraint(["last_attendance_office_id"], ["attendance_office.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "first_attendance_office_id",
            name="uq_office_printed_range_first_attendance_office_id",
        ),
    )
    op.create_index(
        "ix_office_printed_range_speaker_id", "office_printed_range", ["speaker_id"]
    )
    op.create_table(
        "report_put_to",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("office_printed", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("printed_text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "source",
            postgresql.ENUM(
                *_REPORT_PUT_TO_SOURCE_NAMES,
                name="reportputtosource",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("first_ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "sprs_report_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.ForeignKeyConstraint(["sprs_report_id"], ["report.report_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sprs_report_id", "ordinal", name="uq_report_put_to_sprs_report_id_ordinal"
        ),
    )
    op.create_index("ix_report_put_to_office_printed", "report_put_to", ["office_printed"])
    op.create_index("ix_report_put_to_sprs_report_id", "report_put_to", ["sprs_report_id"])
    op.create_table(
        "ministry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_ministry_name"),
    )
    op.create_table(
        "office_title_ministry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("office_printed", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "source",
            postgresql.ENUM(
                *_OFFICE_TITLE_MINISTRY_SOURCE_NAMES,
                name="officetitleministrysource",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("ministry_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["ministry_id"], ["ministry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "office_printed",
            "ministry_id",
            name="uq_office_title_ministry_office_printed_ministry_id",
        ),
    )
    op.create_index(
        "ix_office_title_ministry_office_printed",
        "office_title_ministry",
        ["office_printed"],
    )
    op.create_index(
        "ix_office_title_ministry_ministry_id", "office_title_ministry", ["ministry_id"]
    )
    op.create_table(
        "ministry_see_also",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("note", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_url", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ministry_id", sa.Integer(), nullable=False),
        sa.Column("see_also_ministry_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["ministry_id"], ["ministry.id"]),
        sa.ForeignKeyConstraint(["see_also_ministry_id"], ["ministry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ministry_id", "see_also_ministry_id", name="uq_ministry_see_also_pair"
        ),
    )


def downgrade() -> None:
    op.drop_table("ministry_see_also")
    op.drop_index(
        "ix_office_title_ministry_ministry_id", table_name="office_title_ministry"
    )
    op.drop_index(
        "ix_office_title_ministry_office_printed", table_name="office_title_ministry"
    )
    op.drop_table("office_title_ministry")
    op.drop_table("ministry")
    op.drop_index("ix_report_put_to_sprs_report_id", table_name="report_put_to")
    op.drop_index("ix_report_put_to_office_printed", table_name="report_put_to")
    op.drop_table("report_put_to")
    op.drop_index(
        "ix_office_printed_range_speaker_id", table_name="office_printed_range"
    )
    op.drop_table("office_printed_range")
    op.drop_table("attendance_office")
    postgresql.ENUM(name="officetitleministrysource").drop(op.get_bind())
    postgresql.ENUM(name="reportputtosource").drop(op.get_bind())
    postgresql.ENUM(name="attendanceofficesource").drop(op.get_bind())
