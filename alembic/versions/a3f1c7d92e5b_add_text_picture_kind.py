"""add text picture kind

Revision ID: a3f1c7d92e5b
Revises: 79cd2ef32c09
Create Date: 2026-11-21 19:00:00.000000

"""

from typing import Optional, Sequence, Union

from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a3f1c7d92e5b"
down_revision: Optional[Union[str, Sequence[str]]] = "79cd2ef32c09"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_OLD_PICTURE_KIND_NAMES = ("TABLE", "DIVISION_LIST", "OTHER")


def upgrade() -> None:
    op.execute("ALTER TYPE picturekind ADD VALUE 'TEXT' BEFORE 'OTHER'")


def downgrade() -> None:
    op.execute("ALTER TYPE picturekind RENAME TO picturekind_old")
    postgresql.ENUM(*_OLD_PICTURE_KIND_NAMES, name="picturekind").create(op.get_bind())
    op.execute(
        "ALTER TABLE report_picture ALTER COLUMN kind TYPE picturekind "
        "USING kind::text::picturekind"
    )
    op.execute("DROP TYPE picturekind_old")
