"""add leave and seat tables

Revision ID: e3b7c1d94a62
Revises: d9e4f2a7b3c1
Create Date: 2026-11-09 09:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e3b7c1d94a62"
down_revision: Optional[Union[str, Sequence[str]]] = "d9e4f2a7b3c1"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_LEAVE_ENTRY_FORMAT_NAMES = (
    "STRUCTURED_LIST",
    "PROSE_RANGE",
    "PROSE_SINGLE_DAY",
    "PROSE_DAY_LIST",
    "PROSE_DURATION",
    "TABLE_ROW",
    "UNREAD",
)
_LEAVE_NAME_SOURCE_NAMES = ("PRINTED", "CARRIED_FROM_ROW_ABOVE", "NONE")
_LEAVE_YEAR_SOURCE_NAMES = (
    "NEAREST_TO_SITTING",
    "PRINTED_IN_ENTRY",
    "PRINTED_COLUMN_HEADING",
)
_LEAVE_SPEAKER_LINK_SOURCE_NAMES = ("ROSTER_NAME", "SITTING_ATTENDANCE_ENTRY")
_LEAVE_OFFICE_SOURCE_NAMES = ("PRINTED_ON_ENTRY", "ATTENDANCE_LIST")


def upgrade() -> None:
    postgresql.ENUM(*_LEAVE_ENTRY_FORMAT_NAMES, name="leaveentryformat").create(
        op.get_bind()
    )
    postgresql.ENUM(*_LEAVE_NAME_SOURCE_NAMES, name="leavenamesource").create(
        op.get_bind()
    )
    postgresql.ENUM(*_LEAVE_YEAR_SOURCE_NAMES, name="leaveyearsource").create(
        op.get_bind()
    )
    postgresql.ENUM(
        *_LEAVE_SPEAKER_LINK_SOURCE_NAMES, name="leavespeakerlinksource"
    ).create(op.get_bind())
    postgresql.ENUM(*_LEAVE_OFFICE_SOURCE_NAMES, name="leaveofficesource").create(
        op.get_bind()
    )
    op.create_table(
        "leave_period",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("period_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("end_text", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_key", name="uq_leave_period_period_key"),
    )
    op.create_index("ix_leave_period_start_date", "leave_period", ["start_date"])
    op.create_table(
        "leave_period_printing",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("sitting_date", sa.Date(), nullable=False),
        sa.Column("printed_name", sa.Text(), nullable=True),
        sa.Column("carried_name", sa.Text(), nullable=True),
        sa.Column("printed_from", sa.Text(), nullable=True),
        sa.Column("printed_to", sa.Text(), nullable=True),
        sa.Column("printed_line", sa.Text(), nullable=True),
        sa.Column("printed_heading_from", sa.Text(), nullable=True),
        sa.Column("printed_heading_to", sa.Text(), nullable=True),
        sa.Column("office_printed", sa.Text(), nullable=True),
        sa.Column(
            "entry_format",
            postgresql.ENUM(
                *_LEAVE_ENTRY_FORMAT_NAMES, name="leaveentryformat", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "name_source",
            postgresql.ENUM(
                *_LEAVE_NAME_SOURCE_NAMES, name="leavenamesource", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "year_source",
            postgresql.ENUM(
                *_LEAVE_YEAR_SOURCE_NAMES, name="leaveyearsource", create_type=False
            ),
            nullable=True,
        ),
        sa.Column(
            "speaker_link_source",
            postgresql.ENUM(
                *_LEAVE_SPEAKER_LINK_SOURCE_NAMES,
                name="leavespeakerlinksource",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "office_source",
            postgresql.ENUM(
                *_LEAVE_OFFICE_SOURCE_NAMES,
                name="leaveofficesource",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("is_covering_sitting", sa.Boolean(), nullable=True),
        sa.Column("sitting_id", sa.Integer(), nullable=False),
        sa.Column("leave_period_id", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["sitting_id"], ["sitting.id"]),
        sa.ForeignKeyConstraint(["leave_period_id"], ["leave_period.id"]),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "sitting_id", "ordinal", name="uq_leave_period_printing_sitting_id_ordinal"
        ),
    )
    op.create_index(
        "ix_leave_period_printing_sitting_date",
        "leave_period_printing",
        ["sitting_date"],
    )
    op.create_index(
        "ix_leave_period_printing_sitting_id", "leave_period_printing", ["sitting_id"]
    )
    op.create_index(
        "ix_leave_period_printing_leave_period_id",
        "leave_period_printing",
        ["leave_period_id"],
    )
    op.create_index(
        "ix_leave_period_printing_speaker_id", "leave_period_printing", ["speaker_id"]
    )
    op.create_table(
        "seat_holding",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("division_key", sa.Text(), nullable=False),
        sa.Column("location_name", sa.Text(), nullable=False),
        sa.Column("first_sitting_date", sa.Date(), nullable=False),
        sa.Column("last_sitting_date", sa.Date(), nullable=False),
        sa.Column("sitting_count", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "division_key", "speaker_id", name="uq_seat_holding_division_key_speaker_id"
        ),
    )
    op.create_index("ix_seat_holding_speaker_id", "seat_holding", ["speaker_id"])


def downgrade() -> None:
    op.drop_index("ix_seat_holding_speaker_id", table_name="seat_holding")
    op.drop_table("seat_holding")
    op.drop_index(
        "ix_leave_period_printing_speaker_id", table_name="leave_period_printing"
    )
    op.drop_index(
        "ix_leave_period_printing_leave_period_id", table_name="leave_period_printing"
    )
    op.drop_index(
        "ix_leave_period_printing_sitting_id", table_name="leave_period_printing"
    )
    op.drop_index(
        "ix_leave_period_printing_sitting_date", table_name="leave_period_printing"
    )
    op.drop_table("leave_period_printing")
    op.drop_index("ix_leave_period_start_date", table_name="leave_period")
    op.drop_table("leave_period")
    postgresql.ENUM(name="leaveofficesource").drop(op.get_bind())
    postgresql.ENUM(name="leavespeakerlinksource").drop(op.get_bind())
    postgresql.ENUM(name="leaveyearsource").drop(op.get_bind())
    postgresql.ENUM(name="leavenamesource").drop(op.get_bind())
    postgresql.ENUM(name="leaveentryformat").drop(op.get_bind())
