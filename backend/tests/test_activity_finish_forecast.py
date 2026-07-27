import os
import sys
from datetime import datetime
from pathlib import Path
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from engine.graph.tools import ActivityFinishForecastArguments, model_tool_schemas
from engine.tools.simulation_tools import sim_forecast_activity_finishes
import models


class ActivityFinishForecastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=engine)
        cls.Session = sessionmaker(bind=engine)

    def setUp(self):
        self.db = self.Session()
        for table in reversed(Base.metadata.sorted_tables):
            self.db.execute(table.delete())

        self.db.add(models.P6Project(
            p6_object_id=100,
            project_id="PROJECT-X",
            name="Project X",
            status="Active",
            data_date=datetime(2026, 7, 15),
            last_synced_at=datetime(2026, 7, 16),
        ))
        self.db.add_all([
            self.activity(
                1, "A-1", "Completed", datetime(2026, 7, 5),
                actual_finish=datetime(2026, 7, 5),
                baseline_finish=datetime(2026, 7, 1),
                percent_complete=1.0,
            ),
            self.activity(
                2, "A-2", "In Progress", datetime(2026, 7, 20),
                actual_start=datetime(2026, 7, 1),
                baseline_finish=datetime(2026, 7, 18),
                percent_complete=0.75,
            ),
            self.activity(
                3, "A-3", "In Progress", datetime(2026, 7, 25),
                actual_start=datetime(2026, 6, 1),
                baseline_finish=datetime(2026, 7, 10),
                percent_complete=0.20,
                total_float=0,
                is_critical=True,
            ),
            self.activity(
                4, "A-4", "Not Started", datetime(2026, 7, 28),
                baseline_finish=datetime(2026, 7, 20),
                percent_complete=0,
            ),
            self.activity(
                5, "A-5", "Not Started", datetime(2026, 8, 5),
                baseline_finish=datetime(2026, 8, 5),
                percent_complete=0,
            ),
            self.activity(
                6, "A-6", "In Progress", datetime(2026, 6, 30),
                baseline_finish=datetime(2026, 6, 20),
                percent_complete=0,
            ),
            self.activity(
                7, "A-7", "Completed", datetime(2026, 6, 10),
                actual_finish=datetime(2026, 6, 10),
                baseline_finish=datetime(2026, 6, 1),
                percent_complete=100,
            ),
            self.activity(
                8, "A-8", "Completed", datetime(2026, 5, 5),
                actual_finish=datetime(2026, 5, 5),
                baseline_finish=datetime(2026, 5, 5),
                percent_complete=100,
            ),
            self.activity(9, "A-9", "Not Started", None, percent_complete=0),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()

    @staticmethod
    def activity(
        object_id,
        activity_id,
        status,
        finish,
        *,
        actual_start=None,
        actual_finish=None,
        baseline_finish=None,
        percent_complete=None,
        total_float=40,
        is_critical=False,
    ):
        return models.P6Activity(
            p6_object_id=object_id,
            project_object_id=100,
            activity_id=activity_id,
            name=f"Activity {activity_id}",
            status=status,
            finish_date=finish,
            planned_finish_date=baseline_finish,
            baseline_finish_date=baseline_finish,
            actual_start_date=actual_start,
            actual_finish_date=actual_finish,
            percent_complete=percent_complete,
            total_float=total_float,
            is_critical=is_critical,
        )

    def test_monthly_forecast_reports_exact_target_and_grounded_range(self):
        result = sim_forecast_activity_finishes(
            self.db,
            "PROJECT-X",
            period="month",
            target_year=2026,
            target_month=7,
        )

        self.assertEqual(result["target_period"], {
            "type": "month",
            "year": 2026,
            "month": 7,
            "label": "July 2026",
            "start": "2026-07-01",
            "end_exclusive": "2026-08-01",
        })
        self.assertEqual(result["p6_schedule_target"]["scheduled_to_finish"], 4)
        self.assertEqual(result["p6_schedule_target"]["confirmed_finished_in_cohort"], 1)
        self.assertEqual(result["p6_schedule_target"]["remaining_scheduled"], 3)
        self.assertEqual(result["prediction"]["pace_supported_likely"], 1)
        self.assertEqual(result["prediction"]["pace_at_risk"], 1)
        self.assertEqual(result["prediction"]["schedule_only_candidates"], 1)
        self.assertEqual(
            result["prediction"]["likely_finish_range_by_period_end"],
            {"minimum_evidence_supported": 2, "maximum_if_schedule_only_candidates_hold": 3},
        )
        self.assertEqual(result["prediction"]["outlook"], "HIGH_RISK")
        self.assertEqual(result["prediction"]["confidence"], "MEDIUM")
        self.assertEqual(result["schedule_pressure"]["overdue_carry_in_before_period"], 1)
        self.assertEqual(result["schedule_pressure"]["critical_remaining_due"], 1)
        self.assertEqual(result["historical_delivery"]["completed_sample"], 3)
        self.assertEqual(result["historical_delivery"]["on_time_within_7_days_pct"], 66.7)
        self.assertEqual(result["activities"][0]["activity_id"], "A-3")
        self.assertEqual(
            result["activities"][0]["forecast_bucket"],
            "pace_at_risk_beyond_period_end",
        )

    def test_yearly_forecast_uses_full_calendar_year(self):
        result = sim_forecast_activity_finishes(
            self.db,
            "PROJECT-X",
            period="year",
            target_year=2026,
        )

        self.assertEqual(result["target_period"]["type"], "year")
        self.assertEqual(result["target_period"]["label"], "2026")
        self.assertEqual(result["target_period"]["start"], "2026-01-01")
        self.assertEqual(result["target_period"]["end_exclusive"], "2027-01-01")
        self.assertEqual(result["p6_schedule_target"]["scheduled_to_finish"], 8)
        self.assertEqual(result["p6_schedule_target"]["confirmed_finished_in_cohort"], 3)
        self.assertEqual(result["p6_schedule_target"]["remaining_scheduled"], 5)
        self.assertEqual(
            result["prediction"]["likely_finish_range_by_period_end"],
            {"minimum_evidence_supported": 4, "maximum_if_schedule_only_candidates_hold": 7},
        )

    def test_period_arguments_are_strict_and_tool_is_registered(self):
        valid = ActivityFinishForecastArguments.model_validate({
            "project_id": "PROJECT-X",
            "period": "year",
            "target_year": 2027,
        })
        self.assertEqual(valid.target_year, 2027)
        with self.assertRaises(ValidationError):
            ActivityFinishForecastArguments.model_validate({
                "project_id": "PROJECT-X",
                "period": "year",
                "target_year": 2027,
                "target_month": 7,
            })
        with self.assertRaises(ValidationError):
            ActivityFinishForecastArguments.model_validate({
                "project_id": "PROJECT-X",
                "period": "month",
                "target_year": 2027,
            })

        schemas = {
            item["function"]["name"]: item["function"]
            for item in model_tool_schemas()
        }
        self.assertIn("sim_forecast_activity_finishes", schemas)
        self.assertIn(
            "period",
            schemas["sim_forecast_activity_finishes"]["parameters"]["properties"],
        )


if __name__ == "__main__":
    unittest.main()
