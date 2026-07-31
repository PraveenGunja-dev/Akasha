import sys
from pathlib import Path
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models


class Phase9MigrationTests(unittest.TestCase):
    def test_source_sync_state_migration_matches_model(self):
        migration = (
            BACKEND_DIR / "migrations" / "phase9_source_sync_state.sql"
        ).read_text(encoding="utf-8").lower()
        table = models.SourceSyncState.__table__

        self.assertIn("create table if not exists source_sync_state", migration)
        self.assertEqual(
            set(table.columns.keys()),
            {"source_system", "sync_version", "data_as_of", "last_synced_at"},
        )
        self.assertTrue(table.c.source_system.primary_key)
        self.assertFalse(table.c.sync_version.nullable)
        self.assertFalse(table.c.last_synced_at.nullable)


if __name__ == "__main__":
    unittest.main()
