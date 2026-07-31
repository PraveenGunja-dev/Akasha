import os
import sys
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

with patch.dict(sys.modules, {"msal": MagicMock()}):
    from routers import sync


class SyncFreshnessHookTests(unittest.TestCase):
    def test_successful_p6_sync_marks_version_then_clears_caches(self):
        db = MagicMock()
        cutoff = datetime(2026, 7, 20)
        db.query.return_value.scalar.return_value = cutoff
        result = {"projects_synced": 2, "baselines_synced": 1}

        with patch.object(sync, "P6Service") as service_type, patch.object(
            sync, "mark_source_sync_succeeded"
        ) as mark_success, patch.object(sync, "_clear_p6_caches") as clear_caches:
            events = []
            mark_success.side_effect = lambda *args, **kwargs: events.append("mark")
            clear_caches.side_effect = lambda: events.append("clear")
            service_type.return_value.full_sync.return_value = result
            response = sync.sync_p6_data(db=db)

        self.assertEqual(response["status"], "success")
        mark_success.assert_called_once_with(db, "P6", data_as_of=cutoff)
        clear_caches.assert_called_once_with()
        self.assertEqual(events, ["mark", "clear"])

    def test_failed_p6_sync_does_not_mark_or_clear(self):
        db = MagicMock()

        with patch.object(sync, "P6Service") as service_type, patch.object(
            sync, "mark_source_sync_succeeded"
        ) as mark_success, patch.object(sync, "_clear_p6_caches") as clear_caches:
            service_type.return_value.full_sync.side_effect = RuntimeError("failed")
            with self.assertRaises(sync.HTTPException):
                sync.sync_p6_data(db=db)

        mark_success.assert_not_called()
        clear_caches.assert_not_called()


if __name__ == "__main__":
    unittest.main()
