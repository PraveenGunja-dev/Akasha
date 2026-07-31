import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from engine import cache


class CacheVersionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        cache._hot_cache.clear()

    def tearDown(self):
        self.db.close()

    def test_hot_cache_is_rejected_when_shared_source_version_changes(self):
        initial = {
            "p6_synced_at": None, "sap_synced_at": None, "tc_synced_at": None,
            "pulse_synced_at": None, "p6_sync_version": 1, "sap_sync_version": None,
            "tc_sync_version": None, "pulse_sync_version": None,
            "mapping_sync_version": None, "capacity_sync_version": None,
        }
        cache.update_cache(self.db, "P-1", "project_360", {"value": 1}, initial)

        with patch.object(cache, "get_current_sync_times", return_value={**initial, "p6_sync_version": 2}):
            self.assertTrue(cache.check_freshness(self.db, "P-1")["is_stale"])
            self.assertIsNone(cache.get_cached_data(self.db, "P-1"))


if __name__ == "__main__":
    unittest.main()
