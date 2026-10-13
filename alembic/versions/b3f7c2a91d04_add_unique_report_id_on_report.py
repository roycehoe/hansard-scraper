"""add unique report_id on report

Revision ID: b3f7c2a91d04
Revises: a7c1d4e9b206
Create Date: 2026-10-13 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b3f7c2a91d04'
down_revision: Union[str, Sequence[str], None] = 'a7c1d4e9b206'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The raw table keeps every search hit as received, repeats included, so it gets a plain index.
    op.create_unique_constraint('report_report_id_key', 'report', ['report_id'])
    op.create_index('ix_hansardwebsiteresponse_report_id', 'hansardwebsiteresponse', ['report_id'])


def downgrade() -> None:
    op.drop_index('ix_hansardwebsiteresponse_report_id', table_name='hansardwebsiteresponse')
    op.drop_constraint('report_report_id_key', 'report', type_='unique')
