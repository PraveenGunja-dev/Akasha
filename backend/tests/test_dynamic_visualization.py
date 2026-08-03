import os
import sys
from datetime import datetime
from pathlib import Path
import unittest

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import Base
import models
from engine.graph.tools import ChartArguments
from engine.agent import build_chart_result
from services.dynamic_visualization import (
    VisualizationQueryError,
    VisualizationQueryV2,
    VisualizationSpecV2,
    build_dynamic_visualization,
)


class DynamicVisualizationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(models.ProjectMapping(
            project_id="P-1",
            project="Project One",
            project_name_from_p6="Project One",
            module_wbs="ROOT-1",
        ))
        self.db.add(models.P6Project(
            p6_object_id=1,
            project_id="P-1",
            name="Project One",
            duration_percent_complete=0.5,
            finish_date=datetime(2026, 9, 30),
            baseline_finish_date=datetime(2026, 8, 31),
            data_date=datetime(2026, 8, 1),
        ))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_heatmap_is_aggregated_from_authorized_p6_rows(self):
        self.db.add_all([
            models.P6Activity(
                p6_object_id=10,
                project_object_id=1,
                activity_id="A-1",
                name="Foundation 1",
                status="In Progress",
                wbs_name="BLOCK-01",
                baseline_finish_date=datetime(2026, 7, 1),
                finish_date=datetime(2026, 8, 1),
            ),
            models.P6Activity(
                p6_object_id=11,
                project_object_id=1,
                activity_id="A-2",
                name="Foundation 2",
                status="In Progress",
                wbs_name="BLOCK-01",
                baseline_finish_date=datetime(2026, 7, 2),
                finish_date=datetime(2026, 8, 2),
            ),
        ])
        self.db.commit()

        chart = build_dynamic_visualization(self.db, {
            "dataset_id": "p6.delayed_activities",
            "metrics": [{"field": "delayed_activity_count", "aggregation": "sum"}],
            "dimensions": ["finish_month", "block"],
            "preferred_shape": "heatmap",
        }, project_id="P-1")

        spec = chart["visualization_spec"]
        self.assertEqual(spec["schema_version"], "visualization.v2")
        self.assertEqual(spec["shape"], "heatmap")
        self.assertEqual(spec["data"], [{
            "finish_month": "2026-08",
            "block": "BLOCK-01",
            "delayed_activity_count": 2,
        }])
        self.assertNotIn("option", chart)
        self.assertTrue(spec["spec_hash"].startswith("sha256:"))

        integrated, confirmation = build_chart_result(self.db, {
            "project_id": "P-1",
            "visualization_query": {
                "dataset_id": "p6.delayed_activities",
                "metrics": [{"field": "delayed_activity_count", "aggregation": "sum"}],
                "dimensions": ["finish_month", "block"],
                "preferred_shape": "heatmap",
            },
        })
        self.assertEqual(integrated["schema_version"], "visualization.v2")
        self.assertIn('"schema_version": "visualization.v2"', confirmation)

    def test_curated_procurement_schedule_chart_uses_two_unit_axes(self):
        self.db.add(models.MTPOAmount(
            wbs_element="ROOT-1",
            material_name="Modules",
            order_quantity=10,
            delivered_qty=6,
            still_to_deliver_qty=4,
        ))
        self.db.commit()

        chart = build_dynamic_visualization(self.db, {
            "dataset_id": "portfolio.procurement_schedule",
            "metrics": [
                {"field": "procurement_fulfillment_pct", "aggregation": "avg"},
                {"field": "schedule_delay_days", "aggregation": "avg"},
            ],
            "dimensions": ["project_name"],
            "preferred_shape": "bar",
        }, project_ids=["P-1"])

        spec = chart["visualization_spec"]
        self.assertEqual([channel["axis_index"] for channel in spec["encoding"]["y"]], [0, 1])
        self.assertEqual(spec["data"][0]["procurement_fulfillment_pct"], 60)
        self.assertEqual(spec["data"][0]["schedule_delay_days"], 30)

    def test_invalid_fields_shapes_and_executable_members_are_rejected(self):
        with self.assertRaises(VisualizationQueryError):
            build_dynamic_visualization(self.db, {
                "dataset_id": "p6.block_progress",
                "metrics": [{"field": "not_a_metric"}],
                "dimensions": ["block"],
            }, project_id="P-1")

        self.db.add(models.P6WBSNode(
            p6_object_id=20,
            project_object_id=1,
            wbs_name="BLOCK-01",
        ))
        self.db.add(models.P6Activity(
            p6_object_id=21,
            project_object_id=1,
            wbs_object_id=20,
            activity_id="A-21",
            status="In Progress",
            percent_complete=0.5,
        ))
        self.db.commit()
        with self.assertRaises(VisualizationQueryError):
            build_dynamic_visualization(self.db, {
                "dataset_id": "p6.block_progress",
                "metrics": [{"field": "progress_pct"}],
                "dimensions": ["block"],
                "preferred_shape": "heatmap",
            }, project_id="P-1")

        payload = {
            "schema_version": "visualization.v2",
            "chart_id": "test",
            "chart_type": "test",
            "shape": "bar",
            "title": "Test",
            "summary": "Test",
            "accessibility_description": "Test",
            "encoding": {"y": []},
            "data": [],
            "source_tables": [],
            "javascript_formatter": "alert(1)",
        }
        with self.assertRaises(ValidationError):
            VisualizationSpecV2.model_validate(payload)

    def test_chart_arguments_require_exactly_one_version(self):
        ChartArguments.model_validate({"chart_type": "auto"})
        ChartArguments.model_validate({
            "visualization_query": {
                "dataset_id": "portfolio.risk",
                "metrics": [{"field": "risk_level"}],
                "dimensions": ["project_name"],
            },
        })
        with self.assertRaises(ValidationError):
            ChartArguments.model_validate({})
        with self.assertRaises(ValidationError):
            ChartArguments.model_validate({
                "chart_type": "auto",
                "visualization_query": {
                    "dataset_id": "portfolio.risk",
                    "metrics": [{"field": "risk_level"}],
                },
            })

    def test_query_contract_rejects_unknown_or_code_fields(self):
        with self.assertRaises(ValidationError):
            VisualizationQueryV2.model_validate({
                "dataset_id": "portfolio.risk",
                "metrics": [{"field": "risk_level"}],
                "javascript": "alert(1)",
            })


if __name__ == "__main__":
    unittest.main()
