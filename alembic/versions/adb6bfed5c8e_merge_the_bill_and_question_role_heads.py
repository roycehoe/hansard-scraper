"""merge the bill and question role heads

Revision ID: adb6bfed5c8e
Revises: a7d3e9f1b264, 287f3a4e2fdd
Create Date: 2026-11-06 10:38:47.844273

"""

from typing import Optional, Sequence, Union

revision: str = "adb6bfed5c8e"
down_revision: Optional[Union[str, Sequence[str]]] = ("a7d3e9f1b264", "287f3a4e2fdd")
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
