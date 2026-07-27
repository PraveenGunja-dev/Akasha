import os
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from engine.kpi_engine import compute_schedule_kpis
from engine.tools.p6_tools import p6_get_activities, p6_get_project_summary
import models


def activity(status, *, baseline_finish=None, finish=None, total_float=8):
    return SimpleNamespace(
        status=status,
        baseline_finish_date=baseline_finish,
        finish_date=finish,
        total_float=total_float,
    )


class P6ScheduleAccuracyTests(unittest.TestCase):
    def test_duration_progress_is_not_replaced_by_activity_count_ratio(self):
        p6 = SimpleNamespace(
            duration_percent_complete=0.2309585217391305,
            schedule_performance_index=None,
            cost_performance_index=None,
            data_date=datetime(2026, 7, 18),
            last_synced_at=datetime(2026, 7, 22),
            status="Active",
            scheduled_finish_date=datetime(2027, 10, 1),
        )
        activities = [activity("Completed") for _ in range(486)]
        activities.extend(activity("In Progress") for _ in range(84))
        activities.extend(activity("Not Started") for _ in range(1730))

        result = compute_schedule_kpis(p6, activities)

        self.assertEqual(result["progress_pct"], 23.1)
        self.assertEqual(result["activity_completion_pct"], 21.1)
        self.assertEqual(result["in_progress_activities"], 84)
        self.assertEqual(result["not_started_activities"], 1730)
        self.assertEqual(result["project_status"], "Active")
        self.assertEqual(result["scheduled_finish"], "2027-10-01T00:00:00")
        self.assertEqual(result["last_synced_at"], "2026-07-22T00:00:00")
        self.assertIsNone(result["spi"])
        self.assertIsNone(result["cpi"])
        self.assertIsNone(result["planned_pct"])
        self.assertIsNone(result["schedule_variance_pct"])
        self.assertEqual(result["schedule_status"], "UNKNOWN")
        self.assertIn("SPI is unavailable", result["performance_limitation"])


class P6ToolAccuracyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        db = self.Session()
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        project = models.P6Project(
            p6_object_id=5256,
            project_id="FY26-P18",
            name="AGE26AL_S06A_FT_234MW_PPA",
            status="Active",
            scheduled_finish_date=datetime(2027, 10, 1, 9),
            data_date=datetime(2026, 7, 18, 18),
            duration_percent_complete=0.2309585217391305,
            activity_count=3,
            completed_activity_count=1,
            in_progress_activity_count=2,
            not_started_activity_count=0,
            last_synced_at=datetime(2026, 7, 22, 5, 7),
        )
        db.add(project)
        db.add_all([
            models.P6Activity(
                p6_object_id=1,
                project_object_id=5256,
                activity_id="A-003",
                name="Third activity",
                status="In Progress",
                percent_complete=0.4,
            ),
            models.P6Activity(
                p6_object_id=2,
                project_object_id=5256,
                activity_id="A-001",
                name="First activity",
                status="Completed",
                percent_complete=1.0,
            ),
            models.P6Activity(
                p6_object_id=3,
                project_object_id=5256,
                activity_id="A-002",
                name="Second activity",
                status="In Progress",
                percent_complete=0.75,
            ),
        ])
        db.commit()
        db.close()

    def test_project_summary_normalizes_fractional_duration_progress(self):
        db = self.Session()
        try:
            summary = p6_get_project_summary(db, "FY26-P18")
        finally:
            db.close()
        self.assertEqual(summary["duration_percent_complete"], 23.1)
        self.assertIsNone(summary["spi"])
        self.assertIsNone(summary["cpi"])

    def test_activity_listing_filters_counts_and_orders_results(self):
        db = self.Session()
        try:
            result = p6_get_activities(
                db,
                "FY26-P18",
                status="in_progress",
                limit=100,
            )
        finally:
            db.close()
        self.assertEqual(result["total_matching"], 2)
        self.assertEqual(result["returned"], 2)
        self.assertEqual(
            [row["activity_id"] for row in result["activities"]],
            ["A-002", "A-003"],
        )
        self.assertEqual(result["activities"][0]["percent_complete"], 75.0)
        self.assertEqual(result["last_synced_at"], "2026-07-22T05:07:00")


if __name__ == "__main__":
    unittest.main()
