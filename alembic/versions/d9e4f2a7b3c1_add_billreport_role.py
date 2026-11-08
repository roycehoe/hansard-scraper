"""add billreport role

Revision ID: d9e4f2a7b3c1
Revises: c8d3e1f6a2b9
Create Date: 2026-11-08 23:00:00.000000

"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d9e4f2a7b3c1"
down_revision: Optional[Union[str, Sequence[str]]] = "c8d3e1f6a2b9"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None

_BILL_REPORT_ROLE_NAMES = ("READING", "BUDGET_DEBATE")


def upgrade() -> None:
    postgresql.ENUM(*_BILL_REPORT_ROLE_NAMES, name="billreportrole").create(
        op.get_bind()
    )
    op.add_column(
        "billreport",
        sa.Column(
            "role",
            postgresql.ENUM(
                *_BILL_REPORT_ROLE_NAMES, name="billreportrole", create_type=False
            ),
            nullable=True,
            server_default="READING",
        ),
    )
    op.alter_column("billreport", "role", nullable=False, server_default=None)


def downgrade() -> None:
    op.drop_column("billreport", "role")
    postgresql.ENUM(name="billreportrole").drop(op.get_bind())
