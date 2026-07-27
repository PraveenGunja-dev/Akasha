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
from engine.kpi_engine import (
    compute_evm_metrics,
    compute_health_score,
    compute_project_kpis,
    compute_schedule_kpis,
)
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
        self.assertIn("Native P6 SPI is unavailable", result["performance_limitation"])

    def test_evm_uses_supplied_ac_completion_and_bcws_formulas(self):
        result = compute_evm_metrics(
            actual_cost=800,
            progress_pct=25,
            planned_value=250,
        )

        self.assertEqual(result["earned_value"], 200.0)
        self.assertEqual(result["planned_value"], 250.0)
        self.assertEqual(result["spi"], 0.8)
        self.assertEqual(result["cpi"], 0.25)
        self.assertEqual(result["schedule_variance"], -50.0)
        self.assertEqual(result["cost_variance"], -600.0)

    def test_evm_does_not_default_missing_or_zero_denominators(self):
        missing = compute_evm_metrics(None, 25, 250)
        zero = compute_evm_metrics(0, 25, 0)

        self.assertIsNone(missing["earned_value"])
        self.assertIsNone(missing["spi"])
        self.assertIsNone(missing["cpi"])
        self.assertIsNone(zero["spi"])
        self.assertIsNone(zero["cpi"])

    def test_health_uses_fixed_weights_without_renormalizing(self):
        result = compute_health_score(spi=0.8, cpi=0.25, risk_score=0.9)

        self.assertEqual(result["health_index"], 0.665)
        self.assertEqual(result["health_score"], 66.5)
        self.assertEqual(result["health_status"], "AT RISK")

        unavailable = compute_health_score(spi=0.8, cpi=None, risk_score=0.9)
        self.assertIsNone(unavailable["health_score"])
        self.assertEqual(unavailable["health_status"], "UNKNOWN")


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

    def test_project_summary_keeps_native_p6_performance_indicators(self):
        db = self.Session()
        try:
            project = db.query(models.P6Project).filter(
                models.P6Project.project_id == "FY26-P18"
            ).one()
            project.actual_total_cost = 800
            project.planned_cost = 250
            project.schedule_performance_index = 1.1
            project.cost_performance_index = 0.9
            db.commit()

            summary = p6_get_project_summary(db, "FY26-P18")
        finally:
            db.close()

        self.assertEqual(summary["spi"], 1.1)
        self.assertEqual(summary["cpi"], 0.9)
        self.assertNotIn("earned_value", summary)
        self.assertNotIn("health", summary)

    def test_formula_metrics_require_explicit_project_health_opt_in(self):
        db = self.Session()
        try:
            project = db.query(models.P6Project).filter(
                models.P6Project.project_id == "FY26-P18"
            ).one()
            project.actual_total_cost = 800
            project.planned_cost = 250
            project.schedule_performance_index = 1.1
            project.cost_performance_index = 0.9
            db.commit()

            general = compute_project_kpis(
                db,
                "FY26-P18",
                pos=[],
                tc_total=0,
                calculate_health=False,
            )
            health = compute_project_kpis(
                db,
                "FY26-P18",
                pos=[],
                tc_total=0,
                calculate_health=True,
            )
        finally:
            db.close()

        self.assertEqual(general["schedule"]["spi"], 1.1)
        self.assertNotIn("earned_value", general["schedule"])
        self.assertNotIn("health", general)

        self.assertEqual(health["schedule"]["earned_value"], 184.77)
        self.assertEqual(health["schedule"]["spi"], 0.7391)
        self.assertEqual(health["schedule"]["source_spi"], 1.1)
        self.assertEqual(health["health"]["health_score"], 66.5)

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
