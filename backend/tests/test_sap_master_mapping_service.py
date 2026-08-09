import os
import sys
from pathlib import Path
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models
from services.sap_master_mapping_service import sync_sap_master


TABLES = [models.ProjectMapping.__table__, models.SapProjectScope.__table__]


class SapMasterMappingServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        models.Base.metadata.create_all(cls.engine, tables=TABLES)
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.db = self.Session()
        for table in reversed(TABLES):
            self.db.execute(table.delete())
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def sync(self, *, dry_run=False):
        return sync_sap_master(
            self.db,
            REPO_DIR / "Data" / "AKASHA SAP MASTER FILE.xlsx",
            REPO_DIR / "Data" / "Project_Name_Master.xlsx",
            dry_run=dry_run,
        )

    def test_master_imports_normalized_scopes_and_preserves_name_owner(self):
        report = self.sync()

        self.assertEqual(report.projects_seen, 64)
        self.assertGreater(report.scopes_written, 160)
        self.assertGreaterEqual(report.shared_scope_groups, 13)
        self.assertEqual(self.db.query(models.ProjectMapping).count(), 64)
        p14 = self.db.query(models.ProjectMapping).filter_by(project_id="FY26-P14").one()
        p13 = self.db.query(models.ProjectMapping).filter_by(project_id="FY26-P13").one()
        self.assertEqual(p14.project_name_from_p6, "ASEJ6PL_S07_FT_300MW_PPA")
        self.assertEqual(p13.project_name_from_p6, "FY26-P13")

        shared = self.db.query(models.SapProjectScope).filter_by(
            owner="AGE6L", match_value="H-624A-275"
        ).all()
        self.assertEqual(len(shared), 2)
        self.assertAlmostEqual(sum(scope.allocation_weight for scope in shared), 1.0)

    def test_dry_run_rolls_back_all_changes(self):
        report = self.sync(dry_run=True)

        self.assertEqual(report.projects_seen, 64)
        self.assertEqual(self.db.query(models.ProjectMapping).count(), 0)
        self.assertEqual(self.db.query(models.SapProjectScope).count(), 0)


if __name__ == "__main__":
    unittest.main()
