"""add hand kept bill link source

Revision ID: a7d3e9f1b264
Revises: 4b9e7c2d1a58
Create Date: 2026-11-05 09:00:00.000000

"""

from typing import Optional, Sequence, Union

from alembic import op

revision: str = "a7d3e9f1b264"
down_revision: Optional[Union[str, Sequence[str]]] = "4b9e7c2d1a58"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE billlinksource ADD VALUE IF NOT EXISTS 'HAND_KEPT'")


def downgrade() -> None:
    op.execute("ALTER TYPE billlinksource RENAME TO billlinksource_with_hand_kept")
    op.execute(
        "CREATE TYPE billlinksource AS ENUM ('FIRST_READING_DATE', "
        "'THIRD_READING_DATE', 'SECOND_READING_DATE', 'LOOSE_TITLE_READING_DATES', "
        "'SIMILAR_TITLE_READING_DATES')"
    )
    op.execute(
        "ALTER TABLE acthistoryentry ALTER COLUMN bill_link_source "
        "TYPE billlinksource USING bill_link_source::text::billlinksource"
    )
    op.execute("DROP TYPE billlinksource_with_hand_kept")
