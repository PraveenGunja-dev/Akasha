"""Add missing columns safely

Revision ID: e036d945b869
Revises: 6789335f61d7
Create Date: 2026-06-17 15:34:19.961759

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = 'e036d945b869'
down_revision: Union[str, Sequence[str], None] = '6789335f61d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema safely."""
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    
    # ProjectMapping
    pm_cols = [c['name'] for c in inspector.get_columns('project_mapping')]
    if 'source_of_origin' not in pm_cols:
        op.add_column('project_mapping', sa.Column('source_of_origin', sa.String(), nullable=True))
    if 'priority' not in pm_cols:
        op.add_column('project_mapping', sa.Column('priority', sa.String(), nullable=True))

    # MTPOAmount
    po_cols = [c['name'] for c in inspector.get_columns('mt_poamount')]
    for col_name, col_type in [
        ('material_name', sa.String()),
        ('order_quantity', sa.Float()),
        ('net_order_value_inr', sa.Float()),
        ('still_to_deliver_qty', sa.Float()),
        ('still_to_deliver_inr', sa.Float()),
        ('delivered_qty', sa.Float()),
        ('delivered_value_inr_cr', sa.Float()),
        ('storage_location', sa.String()),
        ('block_plot_name', sa.String()),
        ('currency', sa.String())
    ]:
        if col_name not in po_cols:
            op.add_column('mt_poamount', sa.Column(col_name, col_type, nullable=True))

    # MTInventory
    inv_cols = [c['name'] for c in inspector.get_columns('mt_inventory')]
    for col_name, col_type in [
        ('material_name', sa.String()),
        ('unrestricted_qty', sa.Float())
    ]:
        if col_name not in inv_cols:
            op.add_column('mt_inventory', sa.Column(col_name, col_type, nullable=True))

    # MTMaterialDocument
    md_cols = [c['name'] for c in inspector.get_columns('mt_materialdocument')]
    for col_name, col_type in [
        ('material_name', sa.String()),
        ('material_description', sa.String()),
        ('amount_in_lc', sa.Float()),
        ('amount_in_lc_cr', sa.Float()),
        ('storage_location', sa.String()),
        ('block_plot_name', sa.String()),
        ('purchase_order', sa.String()),
        ('base_unit', sa.String())
    ]:
        if col_name not in md_cols:
            op.add_column('mt_materialdocument', sa.Column(col_name, col_type, nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    pass
