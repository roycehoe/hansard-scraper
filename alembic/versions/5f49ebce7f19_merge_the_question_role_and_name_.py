"""merge the question role and name spelling heads

Revision ID: 5f49ebce7f19
Revises: adb6bfed5c8e, c2f4a8d6e1b3
Create Date: 2026-11-06 23:43:12.007242

"""

from typing import Optional, Sequence, Union

revision: str = "5f49ebce7f19"
down_revision: Optional[Union[str, Sequence[str]]] = ("adb6bfed5c8e", "c2f4a8d6e1b3")
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
