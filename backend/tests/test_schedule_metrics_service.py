import os
import sys
from dataclasses import FrozenInstanceError
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
from services.schedule_metrics_service import (
    ScheduleMetricsService,
    calculate_schedule_metrics,
    get_schedule_metrics,
)
from services.freshness_service import extract_tool_evidence
from engine.tools.p6_tools import (
    p6_get_block_period_progress,
    p6_get_daily_completion_trend,
    p6_get_activity_status_breakdown,
    p6_get_critical_activities,
    p6_get_delayed_activities,
    p6_get_freshness,
    p6_get_project_summary,
)
import models


def project(**overrides):
    values = {
        "project_id": "P-1",
        "actual_non_labor_units": None,
        "at_completion_non_labor_units": None,
        "duration_percent_complete": 0.2,
        "finish_date_variance": None,
        "finish_date": None,
        "baseline_finish_date": None,
        "scheduled_finish_date": None,
        "activity_count": None,
        "completed_activity_count": None,
        "in_progress_activity_count": None,
        "not_started_activity_count": None,
        "data_date": None,
        "last_synced_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class ScheduleMetricsCalculationTests(unittest.TestCase):
    def test_progress_precedence_and_normalization(self):
        units = project(
            actual_non_labor_units=25,
            at_completion_non_labor_units=50,
            construction_percent_complete=0.8,
            duration_percent_complete=0.9,
        )
        construction = project(
            construction_percent_complete=0.42,
            duration_percent_complete=0.9,
        )
        units_overrun = project(
            actual_non_labor_units=125,
            at_completion_non_labor_units=100,
        )

        units_result = calculate_schedule_metrics(units)
        construction_result = calculate_schedule_metrics(construction)
        duration_result = calculate_schedule_metrics(project(duration_percent_complete=72))

        self.assertEqual(units_result.progress_pct, 50.0)
        self.assertEqual(
            units_result.progress_formula,
            "actual_non_labor_units / at_completion_non_labor_units",
        )
        self.assertEqual(units_result.progress_formula_version, "dashboard-progress-v1")
        self.assertEqual(units_result.progress_units, "percent")
        self.assertEqual(construction_result.progress_pct, 42.0)
        self.assertEqual(construction_result.progress_formula, "construction_percent_complete")
        self.assertEqual(duration_result.progress_pct, 72.0)
        self.assertEqual(duration_result.progress_formula, "duration_percent_complete")
        self.assertEqual(calculate_schedule_metrics(units_overrun).progress_pct, 125.0)

    def test_delay_rule_requires_negative_variance_or_late_incomplete_forecast(self):
        late = project(
            duration_percent_complete=0.99,
            finish_date=datetime(2026, 8, 2),
            baseline_finish_date=datetime(2026, 8, 1),
        )
        complete = project(
            duration_percent_complete=1,
            finish_date=datetime(2026, 8, 2),
            scheduled_finish_date=datetime(2026, 8, 1),
        )

        late_result = calculate_schedule_metrics(late)

        self.assertTrue(calculate_schedule_metrics(project(finish_date_variance=-1)).is_delayed)
        self.assertTrue(late_result.is_delayed)
        self.assertEqual(late_result.delay_reference_finish, datetime(2026, 8, 1))
        self.assertEqual(late_result.forecast_vs_reference_days, 1)
        self.assertFalse(calculate_schedule_metrics(complete).is_delayed)

    def test_baseline_finish_has_strict_precedence_over_scheduled_finish(self):
        result = calculate_schedule_metrics(project(
            finish_date=datetime(2026, 8, 5),
            baseline_finish_date=datetime(2026, 8, 10),
            scheduled_finish_date=datetime(2026, 8, 1),
        ))

        self.assertFalse(result.is_delayed)
        self.assertEqual(result.delay_reference_finish, datetime(2026, 8, 10))
        self.assertEqual(result.forecast_vs_reference_days, -5)

    def test_missing_p6_is_explicit_nullable_and_dto_is_frozen(self):
        result = calculate_schedule_metrics(None)

        self.assertFalse(result.p6_available)
        self.assertIsNone(result.progress_pct)
        self.assertIsNone(result.is_delayed)
        self.assertEqual(result.activity_counts["total"], None)
        with self.assertRaises(FrozenInstanceError):
            result.progress_pct = 10


class ScheduleMetricsLookupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_lookup_returns_freshness_and_actual_activity_counts(self):
        db = self.Session()
        db.add(models.P6Project(
            p6_object_id=10,
            project_id="P-10",
            duration_percent_complete=0.25,
            activity_count=99,
            data_date=datetime(2026, 7, 20),
            last_synced_at=datetime(2026, 7, 21),
        ))
        db.add_all([
            models.P6Activity(p6_object_id=1, project_object_id=10, status="Completed"),
            models.P6Activity(p6_object_id=2, project_object_id=10, status="In Progress"),
            models.P6Activity(p6_object_id=3, project_object_id=10, status="Not Started"),
        ])
        db.commit()

        result = get_schedule_metrics(db, "P-10")
        missing = get_schedule_metrics(db, "missing")
        db.close()

        self.assertEqual(result.activity_counts, {
            "total": 3,
            "completed": 1,
            "in_progress": 1,
            "not_started": 1,
        })
        self.assertEqual(result.freshness["data_date"], "2026-07-20T00:00:00")
        self.assertEqual(result.freshness["data_as_of"], "2026-07-20T00:00:00")
        self.assertFalse(missing.p6_available)

    def test_legacy_variance_hours_converts_canonical_days(self):
        db = self.Session()
        db.add(models.P6Project(
            p6_object_id=20,
            project_id="P-20",
            duration_percent_complete=0.5,
            finish_date_variance=-1.5,
        ))
        db.commit()

        result = p6_get_project_summary(db, "P-20")
        db.close()

        self.assertEqual(result["finish_date_variance_days"], -1.5)
        self.assertEqual(result["finish_date_variance_hours"], -36)
        self.assertEqual(result["finish_date_variance_unit"], "days")

    def test_summary_exposes_forecast_variance_and_duration_semantics(self):
        db = self.Session()
        db.add(models.P6Project(
            p6_object_id=21,
            project_id="P-21",
            duration_percent_complete=0.612,
            finish_date=datetime(2026, 7, 6),
            baseline_finish_date=datetime(2026, 3, 26),
            scheduled_finish_date=datetime(2027, 3, 29),
            planned_duration=8424,
            actual_duration=7448,
            remaining_duration=1576,
        ))
        db.commit()

        result = p6_get_project_summary(db, "P-21")
        db.close()

        self.assertEqual(result["forecast_finish"], "2026-07-06T00:00:00")
        self.assertEqual(result["delay_reference_finish"], "2026-03-26T00:00:00")
        self.assertEqual(result["forecast_vs_reference_days"], 102)
        self.assertIn("not earned hours", result["duration_field_semantics"])
        self.assertIn("must not be used to derive progress_pct", result["duration_field_semantics"])

    def test_activity_queries_centralize_pagination_criticality_and_drift(self):
        db = self.Session()
        db.add(models.P6Project(
            p6_object_id=30,
            project_id="P-30",
            data_date=datetime(2026, 7, 20),
        ))
        db.add_all([
            models.P6Activity(
                p6_object_id=1,
                project_object_id=30,
                activity_id="A-2",
                status="In Progress",
                percent_complete=0.25,
                total_float=-2,
                baseline_finish_date=datetime(2026, 7, 1),
                finish_date=datetime(2026, 7, 11),
            ),
            models.P6Activity(
                p6_object_id=2,
                project_object_id=30,
                activity_id="A-1",
                status="Completed",
                percent_complete=1,
                total_float=4,
            ),
        ])
        db.commit()

        page = ScheduleMetricsService.get_activity_page(
            db, "P-30", status="In Progress", limit=1, offset=0
        )
        critical = ScheduleMetricsService.get_critical_activities(db, "P-30")
        delayed = ScheduleMetricsService.get_delayed_activities(
            db, "P-30", min_drift_days=7, limit=1
        )
        critical_tool = p6_get_critical_activities(db, "P-30")
        delayed_tool = p6_get_delayed_activities(db, "P-30", min_drift_days=7)
        status_tool = p6_get_activity_status_breakdown(db, "P-30")
        freshness_tool = p6_get_freshness(db, "P-30")
        db.close()

        self.assertEqual(page["total_matching"], 1)
        self.assertEqual(page["activities"][0]["percent_complete"], 25.0)
        self.assertEqual(critical[0]["activity_id"], "A-2")
        self.assertEqual(critical[0]["drift_days"], 10)
        self.assertTrue(delayed[0]["is_critical"])
        self.assertEqual(critical_tool[0]["total_float_hours"], -2)
        self.assertEqual(delayed_tool[0]["forecast_finish"], "2026-07-11T00:00:00")
        self.assertEqual(status_tool["breakdown"], {"In Progress": 1, "Completed": 1})
        self.assertEqual(freshness_tool["data_date"], "2026-07-20T00:00:00")

    def test_block_period_progress_ranks_completion_events_and_discloses_history_limit(self):
        db = self.Session()
        db.add(models.P6Project(
            p6_object_id=40,
            project_id="P-40",
            name="Block Project",
            data_date=datetime(2026, 7, 20),
            last_synced_at=datetime(2026, 7, 21),
        ))
        db.add_all([
            models.P6WBSNode(p6_object_id=100, project_object_id=40, wbs_name="Construction"),
            models.P6WBSNode(p6_object_id=101, project_object_id=40, parent_object_id=100, wbs_name="BLOCK-01"),
            models.P6WBSNode(p6_object_id=102, project_object_id=40, parent_object_id=101, wbs_name="Civil"),
            models.P6WBSNode(p6_object_id=201, project_object_id=40, parent_object_id=100, wbs_code="BLOCK-02", wbs_name="Electrical Area"),
            models.P6WBSNode(p6_object_id=202, project_object_id=40, parent_object_id=201, wbs_name="Electrical"),
        ])
        db.add_all([
            models.P6Activity(
                p6_object_id=1, project_object_id=40, wbs_object_id=102,
                activity_id="B1-A1", status="Completed", percent_complete=1,
                actual_finish_date=datetime(2026, 6, 10),
            ),
            models.P6Activity(
                p6_object_id=2, project_object_id=40, wbs_object_id=102,
                activity_id="B1-A2", status="In Progress", percent_complete=.5,
            ),
            models.P6Activity(
                p6_object_id=5, project_object_id=40, wbs_object_id=102,
                activity_id="B1-A3", status="Not Started", percent_complete=None,
            ),
            models.P6Activity(
                p6_object_id=3, project_object_id=40, wbs_object_id=202,
                activity_id="B2-A1", status="Completed", percent_complete=1,
                actual_finish_date=datetime(2026, 6, 5),
            ),
            models.P6Activity(
                p6_object_id=4, project_object_id=40, wbs_object_id=202,
                activity_id="B2-A2", status="Completed", percent_complete=1,
                actual_finish_date=datetime(2026, 6, 25),
            ),
        ])
        db.commit()

        result = p6_get_block_period_progress(db, "P-40", "last_month")
        current = p6_get_block_period_progress(db, "P-40", "current_month")
        db.query(models.P6Project).filter_by(project_id="P-40").one().data_date = None
        db.commit()
        fallback = p6_get_block_period_progress(db, "P-40", "last_month")
        db.close()

        self.assertEqual(result["period_start"], "2026-06-01")
        self.assertEqual(result["period_end_exclusive"], "2026-07-01")
        self.assertEqual(result["highest_blocks"], ["BLOCK-02"])
        self.assertEqual(result["highest_progress_pct"], 100.0)
        self.assertFalse(result["historical_percentage_delta_available"])
        block_one = next(block for block in result["blocks"] if block["block"] == "BLOCK-01")
        self.assertEqual(block_one["current_activity_completion_pct"], 75.0)
        self.assertEqual(block_one["activities_with_percent_complete"], 2)
        self.assertIn("p6_wbs_node", result["_source_tables"])
        evidence = extract_tool_evidence(
            result,
            tool_name="p6_get_block_period_progress",
            status="ok",
            project_id="P-40",
        )
        evidence_by_table = {item["source_entity"]: item for item in evidence}
        self.assertIn("B1-A1", evidence_by_table["p6_activity"]["record_ids"])
        self.assertIn("201", evidence_by_table["p6_wbs_node"]["record_ids"])
        self.assertEqual(current["period_start"], "2026-07-01")
        self.assertEqual(current["period_end_exclusive"], "2026-07-21")
        self.assertEqual(set(current["highest_blocks"]), {"BLOCK-01", "BLOCK-02"})
        self.assertEqual(fallback["period_anchor"], "server_date_fallback")
        self.assertTrue(any("server date" in warning for warning in fallback["warnings"]))

    def test_rolling_block_period_and_daily_completion_trend_are_event_based(self):
        db = self.Session()
        db.add(models.P6Project(
            p6_object_id=50,
            project_id="P-50",
            name="Trend Project",
            data_date=datetime(2026, 7, 20),
            last_synced_at=datetime(2026, 7, 21),
        ))
        db.add_all([
            models.P6WBSNode(
                p6_object_id=501, project_object_id=50, wbs_name="BLOCK-01"
            ),
            models.P6WBSNode(
                p6_object_id=502, project_object_id=50, wbs_name="BLOCK-02"
            ),
        ])
        db.add_all([
            models.P6Activity(
                p6_object_id=51, project_object_id=50, wbs_object_id=501,
                activity_id="A-1", status="Completed", percent_complete=1,
                actual_finish_date=datetime(2026, 7, 11),
            ),
            models.P6Activity(
                p6_object_id=52, project_object_id=50, wbs_object_id=501,
                activity_id="A-2", status="Completed", percent_complete=1,
                actual_finish_date=datetime(2026, 7, 20),
            ),
            models.P6Activity(
                p6_object_id=53, project_object_id=50, wbs_object_id=502,
                activity_id="B-1", status="Not Started", percent_complete=0,
            ),
        ])
        db.commit()

        blocks = p6_get_block_period_progress(db, "P-50", "last_n_days", 10)
        trend = p6_get_daily_completion_trend(db, "P-50", 10)
        db.close()

        self.assertEqual(blocks["period_start"], "2026-07-11")
        self.assertEqual(blocks["period_end_exclusive"], "2026-07-21")
        self.assertEqual(blocks["highest_blocks"], ["BLOCK-01"])
        self.assertEqual(blocks["lowest_blocks"], ["BLOCK-02"])
        self.assertEqual(trend["completion_events_in_period"], 2)
        self.assertEqual(trend["daily"][0]["activities_completed"], 1)
        self.assertEqual(trend["daily"][-1]["activities_completed"], 1)
        self.assertFalse(trend["historical_duration_progress_available"])
        self.assertIn("p6_activity", trend["_source_tables"])


if __name__ == "__main__":
    unittest.main()
