"""add minutes tables

Revision ID: 3e8a6d15c2f7
Revises: 7b1f3c9a2e40
Create Date: 2026-11-09 16:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3e8a6d15c2f7"
down_revision: Optional[Union[str, Sequence[str]]] = "7b1f3c9a2e40"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_MINUTES_STATUS_NAMES = (
    "NOT_YET_LISTED",
    "LISTED",
    "TEXT_STORED",
    "FILE_NOT_FOUND",
    "NEEDS_REVIEW",
)
_MINUTES_INDEX_SOURCE_NAMES = (
    "LIVE_PAGE",
    "ARCHIVE_INDEX_CAPTURE",
    "ARCHIVE_FILE_LISTING",
)
_MINUTES_FILE_FORMAT_NAMES = ("PDF", "WORD")


def upgrade() -> None:
    postgresql.ENUM(*_MINUTES_STATUS_NAMES, name="minutesstatus").create(op.get_bind())
    postgresql.ENUM(*_MINUTES_INDEX_SOURCE_NAMES, name="minutesindexsource").create(
        op.get_bind()
    )
    postgresql.ENUM(*_MINUTES_FILE_FORMAT_NAMES, name="minutesfileformat").create(
        op.get_bind()
    )
    op.create_table(
        "minutes_index_capture",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("archive_timestamp", sa.Text(), nullable=True),
        sa.Column("capture_url", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capture_url"),
    )
    op.create_table(
        "minutes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sitting_date", sa.Date(), nullable=False),
        sa.Column("printed_label", sa.Text(), nullable=True),
        sa.Column("printed_parliament", sa.Text(), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=True),
        sa.Column("archive_timestamp", sa.Text(), nullable=True),
        sa.Column(
            "file_format",
            postgresql.ENUM(
                *_MINUTES_FILE_FORMAT_NAMES,
                name="minutesfileformat",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("status_note", sa.Text(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                *_MINUTES_STATUS_NAMES, name="minutesstatus", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "index_source",
            postgresql.ENUM(
                *_MINUTES_INDEX_SOURCE_NAMES,
                name="minutesindexsource",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("index_capture_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["index_capture_id"], ["minutes_index_capture.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sitting_date"),
    )
    op.create_index("ix_minutes_index_capture_id", "minutes", ["index_capture_id"])


def downgrade() -> None:
    op.drop_index("ix_minutes_index_capture_id", table_name="minutes")
    op.drop_table("minutes")
    op.drop_table("minutes_index_capture")
    postgresql.ENUM(name="minutesfileformat").drop(op.get_bind())
    postgresql.ENUM(name="minutesindexsource").drop(op.get_bind())
    postgresql.ENUM(name="minutesstatus").drop(op.get_bind())
