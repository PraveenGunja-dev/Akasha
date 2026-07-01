"""fix_duplicate_projects_and_tc_mappings

Revision ID: 7dc3ca915306
Revises: 71a6d9b3c1b6
Create Date: 2026-06-29 01:34:42.420406

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7dc3ca915306'
down_revision: Union[str, Sequence[str], None] = '71a6d9b3c1b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Remove duplicate/unmapped "Not Found" projects from project_mapping
    op.execute("DELETE FROM project_mapping WHERE project_name_from_p6 IN ('ARE57L_A11_500MW_PPA', 'ARE57L_A12_350MW_PPA');")
    
    # Drop the unused 'tc_project' table
    op.execute("DROP TABLE IF EXISTS tc_project;")
    
    # Update Rajasthan Transmission Mappings (Fatehgarh-III -> BAIYA)
    op.execute("""
        UPDATE tc_network_edge
        SET mapping_id = (SELECT id FROM project_mapping WHERE project_name_from_p6 = 'ASEB1PL_BAIYA_FT_600MW_PPA' LIMIT 1),
            projects = '{"projects": ["ASEB1PL_BAIYA_FT_600MW_PPA"], "phases": []}'
        WHERE region = 'Rajasthan' AND (from_label ILIKE 'Fatehgarh%' OR to_label ILIKE 'Fatehgarh%');
    """)
    
    # Update Rajasthan Transmission Mappings (Ramgarh -> BANDHA)
    op.execute("""
        UPDATE tc_network_edge
        SET mapping_id = (SELECT id FROM project_mapping WHERE project_name_from_p6 = 'AGE25BL_BANDHA_FT_500MW_PPA' LIMIT 1),
            projects = '{"projects": ["AGE25BL_BANDHA_FT_500MW_PPA"], "phases": []}'
        WHERE region = 'Rajasthan' AND (from_label ILIKE 'Ramgarh%' OR to_label ILIKE 'Ramgarh%');
    """)


def downgrade() -> None:
    """Downgrade schema."""
    pass
