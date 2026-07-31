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

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from routers import quality


TABLES = (
    models.ProjectMapping.__table__,
    models.P6Project.__table__,
    models.PulseNC.__table__,
    models.PulseRFI.__table__,
)


class QualityRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine, tables=TABLES)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.add_all([
            models.ProjectMapping(
                id=1,
                project_id="P-ALPHA",
                project="Alpha Site",
                project_name_from_p6="Alpha Schedule",
                spv_name="ALPHA-SPV",
                cluster="Solar North",
                category="Solar",
            ),
            models.ProjectMapping(
                id=2,
                project_id="P-ALPHA-2",
                project="Alpha Extension",
                project_name_from_p6="Alpha Extension",
                spv_name="SHARED-SPV",
                cluster="Solar North",
                category="Solar",
            ),
            models.P6Project(p6_object_id=1, project_id="P-ALPHA", name="Native Alpha"),
            models.PulseNC(
                pulse_id="NC-1",
                status="raised",
                category="critical",
                project_name="Alpha Site",
                spv_name="ALPHA-SPV",
                vendor_name="BuildCo",
                created_at=datetime(2026, 7, 30),
            ),
            models.PulseRFI(
                pulse_id="RFI-1",
                status="completed",
                project_name="Alpha Site",
                spv_name="ALPHA-SPV",
                created_at=datetime(2026, 7, 30),
            ),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_overview_contract_is_additive_and_contractors_remain_a_list(self):
        overview = quality.get_quality_overview(db=self.db)
        contractors = quality.get_contractor_scorecard(db=self.db)
        trends = quality.get_quality_trends(db=self.db)

        self.assertEqual(overview["total_ncs"], 1)
        self.assertIn("availability", overview)
        self.assertIn("provenance", overview)
        self.assertEqual(contractors[0]["name"], "BuildCo")
        self.assertIsInstance(contractors, list)
        self.assertEqual(trends, [{"month": "2026-07", "created": 1, "closed": 0}])

    def test_project_preserves_legacy_name_and_adds_canonical_identity(self):
        result = quality.get_project_quality("P-ALPHA", db=self.db)

        self.assertEqual(result["project_name"], "P-ALPHA")
        self.assertEqual(result["resolved_project_name"], "Alpha Schedule")
        self.assertEqual(result["project_id"], "P-ALPHA")
        self.assertTrue(result["available"])
        self.assertNotIn("candidates", result)

    def test_ambiguous_and_unknown_projects_use_generic_statuses(self):
        with self.assertRaises(HTTPException) as ambiguous:
            quality.get_project_quality("Alpha", db=self.db)
        with self.assertRaises(HTTPException) as missing:
            quality.get_project_quality("does-not-exist", db=self.db)

        self.assertEqual(ambiguous.exception.status_code, 409)
        self.assertNotIn("P-ALPHA", ambiguous.exception.detail)
        self.assertEqual(missing.exception.status_code, 404)

    def test_nc_project_filter_uses_same_resolution_statuses(self):
        arguments = {
            "status": None,
            "category": None,
            "cluster": None,
            "package": None,
            "page": 1,
            "page_size": 50,
            "db": self.db,
        }
        with self.assertRaises(HTTPException) as ambiguous:
            quality.get_nc_list(project="Alpha", **arguments)
        with self.assertRaises(HTTPException) as missing:
            quality.get_nc_list(project="does-not-exist", **arguments)

        self.assertEqual(ambiguous.exception.status_code, 409)
        self.assertEqual(missing.exception.status_code, 404)


class PulseSyncRouteTests(unittest.TestCase):
    @staticmethod
    def sync_router():
        with patch.dict(sys.modules, {"msal": MagicMock()}):
            from routers import sync
        return sync

    def test_successful_sync_clears_dashboard_caches(self):
        sync = self.sync_router()
        with patch("services.pulse_service.PulseService") as service_type, patch(
            "routers.dashboard.clear_dashboard_caches"
        ) as clear_caches, patch.object(
            sync, "mark_source_sync_succeeded"
        ) as mark_success:
            db = MagicMock()
            db.query.return_value.scalar.return_value = None
            service_type.return_value.full_sync.return_value = {
                "ncs": 2,
                "rfis": 3,
                "new_projects": 0,
            }

            result = sync.sync_pulse_data(db=db)

        self.assertEqual(result["status"], "success")
        mark_success.assert_called_once_with(db, "Pulse", data_as_of=None)
        clear_caches.assert_called_once_with()

    def test_failed_sync_does_not_clear_dashboard_caches(self):
        sync = self.sync_router()
        with patch("services.pulse_service.PulseService") as service_type, patch(
            "routers.dashboard.clear_dashboard_caches"
        ) as clear_caches, patch.object(
            sync, "mark_source_sync_succeeded"
        ) as mark_success:
            service_type.return_value.full_sync.side_effect = RuntimeError("failed")

            with self.assertRaises(HTTPException):
                sync.sync_pulse_data(db=object())

        clear_caches.assert_not_called()
        mark_success.assert_not_called()


if __name__ == "__main__":
    unittest.main()
