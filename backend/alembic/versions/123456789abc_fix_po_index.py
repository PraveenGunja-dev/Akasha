"""fix po amount unique index

Revision ID: 123456789abc
Revises: e036d945b869
Create Date: 2026-06-17 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '123456789abc'
down_revision: Union[str, Sequence[str], None] = 'e036d945b869'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Safely drop the existing index regardless of whether it's unique or not
    op.execute("DROP INDEX IF EXISTS ix_mt_poamount_purchasing_document")
    # Recreate the index as NON-UNIQUE
    op.create_index('ix_mt_poamount_purchasing_document', 'mt_poamount', ['purchasing_document'], unique=False)

def downgrade() -> None:
    pass
