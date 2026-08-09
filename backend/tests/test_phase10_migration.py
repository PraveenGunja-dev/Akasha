import sys
from pathlib import Path
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models


class PhaseTenMigrationTests(unittest.TestCase):
    def test_sap_project_scope_migration_matches_model(self):
        migration = (
            BACKEND_DIR / "migrations" / "phase10_sap_project_scope.sql"
        ).read_text(encoding="utf-8").lower()
        table = models.SapProjectScope.__table__

        self.assertIn("create table if not exists sap_project_scope", migration)
        self.assertEqual(
            set(table.columns.keys()),
            {
                "id", "project_mapping_id", "owner", "match_kind", "match_value",
                "allocation_group", "allocation_weight", "source_file", "source_sheet",
                "source_row", "active", "upload_time",
            },
        )
        self.assertFalse(table.c.project_mapping_id.nullable)
        self.assertFalse(table.c.allocation_weight.nullable)


if __name__ == "__main__":
    unittest.main()
