"""add report participant tables

Revision ID: b50219e27a8f
Revises: 52f4f7b77f1f
Create Date: 2026-11-04 08:50:22.543804

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b50219e27a8f"
down_revision: Optional[Union[str, Sequence[str]]] = "52f4f7b77f1f"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_PARTICIPANT_ROLE_NAMES = (
    "ASKER",
    "ABSENT_FILER",
    "READER",
    "ASKER_FOLLOW_UP",
    "SUPPLEMENTARY",
    "ANSWERER",
    "CHAIR",
    "UNLABELLED",
)
_PARTICIPANT_ROLE_SOURCE_NAMES = (
    "ASKER_RULES",
    "CHAIR_LABEL",
    "CHAIR_NAME_CALL",
    "OFFICE_LABEL",
    "OFFICE_ON_THE_DAY",
    "POSITION",
    "AFTER_ANSWER",
    "NO_RULE",
)
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
_OFFICE_SOURCE_NAMES = (
    "LABEL_IN_REPORT",
    "HEADER_IN_REPORT",
    "ATTENDANCE_LIST",
    "LABEL_SAME_DAY",
    "PARLIAMENT_GUESS",
)
_QUESTION_STATE_NAMES = (
    "NOT_ASKED_ALOUD",
    "CORRECTION",
    "URGENT",
    "NOT_A_QUESTION",
)


def upgrade() -> None:
    postgresql.ENUM(*_PARTICIPANT_ROLE_NAMES, name="participantrole").create(
        op.get_bind()
    )
    postgresql.ENUM(
        *_PARTICIPANT_ROLE_SOURCE_NAMES, name="participantrolesource"
    ).create(op.get_bind())
    postgresql.ENUM(*_OFFICE_CLASS_NAMES, name="officeclass").create(op.get_bind())
    postgresql.ENUM(*_OFFICE_SOURCE_NAMES, name="officesource").create(op.get_bind())
    postgresql.ENUM(*_QUESTION_STATE_NAMES, name="questionstate").create(op.get_bind())
    op.create_table(
        "report_participant",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                *_PARTICIPANT_ROLE_NAMES, name="participantrole", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "role_source",
            postgresql.ENUM(
                *_PARTICIPANT_ROLE_SOURCE_NAMES,
                name="participantrolesource",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("first_ordinal", sa.Integer(), nullable=False),
        sa.Column("printed_name", sa.Text(), nullable=False),
        sa.Column("answering_for_printed", sa.Text(), nullable=True),
        sa.Column("office_printed", sa.Text(), nullable=True),
        sa.Column(
            "office_class",
            postgresql.ENUM(
                *_OFFICE_CLASS_NAMES, name="officeclass", create_type=False
            ),
            nullable=True,
        ),
        sa.Column(
            "office_source",
            postgresql.ENUM(
                *_OFFICE_SOURCE_NAMES, name="officesource", create_type=False
            ),
            nullable=True,
        ),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("speaker_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["report.id"]),
        sa.ForeignKeyConstraint(["speaker_id"], ["speaker.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_id", "ordinal", name="uq_report_participant_report_id_ordinal"
        ),
    )
    op.create_index(
        "ix_report_participant_report_id", "report_participant", ["report_id"]
    )
    op.create_index(
        "ix_report_participant_speaker_id", "report_participant", ["speaker_id"]
    )
    op.create_table(
        "report_question_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "state",
            postgresql.ENUM(
                *_QUESTION_STATE_NAMES, name="questionstate", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("printed_text", sa.Text(), nullable=False),
        sa.Column("first_ordinal", sa.Integer(), nullable=True),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["report.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_id", "state", name="uq_report_question_state_report_id_state"
        ),
    )
    op.create_index(
        "ix_report_question_state_report_id", "report_question_state", ["report_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_report_question_state_report_id", table_name="report_question_state"
    )
    op.drop_table("report_question_state")
    op.drop_index("ix_report_participant_speaker_id", table_name="report_participant")
    op.drop_index("ix_report_participant_report_id", table_name="report_participant")
    op.drop_table("report_participant")
    postgresql.ENUM(name="questionstate").drop(op.get_bind())
    postgresql.ENUM(name="officesource").drop(op.get_bind())
    postgresql.ENUM(name="officeclass").drop(op.get_bind())
    postgresql.ENUM(name="participantrolesource").drop(op.get_bind())
    postgresql.ENUM(name="participantrole").drop(op.get_bind())
