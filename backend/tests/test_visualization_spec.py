from pathlib import Path
import os
import sys
import unittest

from pydantic import ValidationError


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.report_renderers import render_visualization_spec
from services.visualization_spec import (
    VisualizationSpecV1,
    block_progress_spec,
    daily_completion_spec,
    planned_vs_actual_progress_spec,
    portfolio_status_spec,
    project_progress_spec,
)


class VisualizationSpecTests(unittest.TestCase):
    def test_daily_spec_is_stable_validated_and_renderer_neutral(self):
        data = {
            "daily": [
                {"date": "2026-07-30", "activities_completed": 2, "cumulative_activity_finish_pct": 20},
                {"date": "2026-07-31", "activities_completed": 3, "cumulative_activity_finish_pct": 30},
            ],
            "completion_events_in_period": 5,
            "period_start": "2026-07-30",
            "period_end_inclusive": "2026-07-31",
            "data_as_of": "2026-07-31",
        }
        spec = daily_completion_spec(data, "Project One")
        self.assertIsNotNone(spec)
        first = spec.transport()
        second = spec.transport()
        self.assertEqual(first["spec_hash"], second["spec_hash"])
        self.assertEqual(first["shape"], "combo")
        self.assertNotIn("option", first)
        self.assertNotIn("formatter", first)
        self.assertEqual(first["series"][0]["values"], [2, 3])
        self.assertEqual(VisualizationSpecV1.model_validate(first).chart_id, "project.daily-completion")

    def test_block_and_portfolio_specs_share_the_same_contract(self):
        block = block_progress_spec({
            "blocks": [
                {"block": "BLOCK-02", "current_activity_completion_pct": 25, "activity_count": 8, "completed_in_period": 1},
                {"block": "BLOCK-01", "current_activity_completion_pct": 80, "activity_count": 10, "completed_in_period": 4},
            ],
            "data_as_of": "2026-07-31",
        }, "Project One")
        progress = project_progress_spec([
            {"project_name": "B", "progress_pct": 40},
            {"project_name": "A", "progress_pct": 75},
        ])
        status = portfolio_status_spec({"delayed": 2, "on_track": 3, "completed": 1, "p6_unavailable": 0})
        self.assertEqual(block.transport()["categories"], ["BLOCK-01", "BLOCK-02"])
        self.assertEqual(progress.transport()["categories"], ["A", "B"])
        self.assertEqual(status.transport()["series"][0]["values"], [2, 3, 1])
        for spec in (block, progress, status):
            image = render_visualization_spec(spec.transport())
            self.assertIsNotNone(image)
            self.assertGreater(len(image.getvalue()), 1_000)

    def test_contract_rejects_renderer_specific_or_unknown_fields(self):
        payload = project_progress_spec([{"project_name": "A", "progress_pct": 75}]).transport()
        payload["javascript_formatter"] = "alert(1)"
        with self.assertRaises(ValidationError):
            VisualizationSpecV1.model_validate(payload)

    def test_planned_vs_actual_spec_is_renderer_neutral_and_traceable(self):
        spec = planned_vs_actual_progress_spec({
            "timeline": [
                {
                    "date": "2026-01-31",
                    "planned_activity_finish_pct": 50,
                    "actual_activity_finish_pct": 25,
                    "variance_pct_points": -25,
                },
            ],
            "current_planned_activity_finish_pct": 50,
            "current_actual_activity_finish_pct": 25,
            "current_variance_pct_points": -25,
            "period_end_inclusive": "2026-01-31",
            "data_as_of": "2026-01-31",
        }, "Project One")

        payload = spec.transport()

        self.assertEqual(payload["chart_type"], "planned_vs_actual_progress")
        self.assertEqual(payload["series"][0]["values"], [50.0])
        self.assertEqual(payload["series"][1]["values"], [25.0])
        self.assertNotIn("formatter", payload)


if __name__ == "__main__":
    unittest.main()
