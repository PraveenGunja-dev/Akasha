import os
import sys
from datetime import datetime
from pathlib import Path
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from database import Base
import models
from engine.tools.p6_tools import p6_get_portfolio_milestone_risks
from engine.tools.viz_tools import build_chart
from engine.agent import build_chart_result
from services.chart_spec_service import ChartSpecService


class ChartSpecServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(models.ProjectMapping(
            project_id="P-1",
            project="Project One",
            project_name_from_p6="Project One P6",
            module_wbs="ROOT",
        ))

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_sap_po_fulfillment_uses_authoritative_material_contract(self):
        self.db.add_all([
            models.MTPOAmount(
                wbs_element="ROOT",
                material_name="Modules",
                order_quantity=10,
                delivered_qty=4,
                still_to_deliver_qty=6,
            ),
            models.MTPOAmount(
                wbs_element="ROOT/LOT-2",
                material_name="Modules",
                order_quantity=5,
                delivered_qty=5,
                still_to_deliver_qty=0,
            ),
        ])
        self.db.commit()

        data = ChartSpecService.sap_po_fulfillment(self.db, "P-1")
        chart = build_chart(self.db, "sap_po_fulfillment", project_id="P-1")

        self.assertEqual(data["rows"], [{
            "name": "Modules", "ordered": 15, "delivered": 9, "pending": 6,
        }])
        self.assertEqual(data["fulfillment_pct"], 60.0)
        self.assertFalse(chart.get("no_data", False))
        self.assertEqual([series["name"] for series in chart["option"]["series"]], ["Delivered", "Pending"])
        self.assertEqual(chart["option"]["series"][0]["data"], [9])
        self.assertEqual(chart["option"]["series"][1]["data"], [6])
        self.assertEqual(chart["option"]["series"][0]["stack"], "ordered")

    def test_project_comparison_uses_canonical_schedule_progress(self):
        self.db.add(models.P6Project(
            p6_object_id=1,
            project_id="P-1",
            actual_non_labor_units=25,
            at_completion_non_labor_units=50,
            duration_percent_complete=0.9,
            planned_duration=1000,
            actual_duration=800,
            remaining_duration=200,
            finish_date=datetime(2026, 8, 28),
            baseline_finish_date=datetime(2025, 9, 1),
            data_date=datetime(2026, 6, 27),
        ))
        self.db.add(models.ProjectMapping(
            project_id="P-2", project="Project Two", project_name_from_p6="Project Two P6"
        ))
        self.db.add(models.P6Project(
            p6_object_id=2, project_id="P-2", duration_percent_complete=0.75,
            planned_duration=1200, actual_duration=900, remaining_duration=300,
            finish_date=datetime(2026, 9, 22), baseline_finish_date=datetime(2026, 6, 27),
            data_date=datetime(2026, 7, 4),
        ))
        self.db.commit()

        chart = build_chart(self.db, "project_comparison", project_ids=["P-1", "P-2"])

        self.assertEqual(chart["option"]["series"][0]["data"], [50.0, 75.0])

        dashboard, confirmation = build_chart_result(self.db, {
            "chart_type": "project_comparison",
            "project_ids": ["P-1", "P-2"],
        })
        self.assertEqual(dashboard["schema_version"], "visualization.bundle.v1")
        self.assertEqual(len(dashboard["charts"]), 4)
        self.assertEqual(
            [chart["chart_type"] for chart in dashboard["charts"]],
            [
                "project_comparison",
                "project_activity_composition",
                "project_duration_comparison",
                "project_baseline_slip",
            ],
        )
        self.assertEqual(
            [chart["visualization_spec"]["shape"] for chart in dashboard["charts"]],
            ["radial_progress", "horizontal_bar", "vertical_bar", "lollipop"],
        )
        self.assertIn('"chart_count": 4', confirmation)
        slips = {
            row["project_name"]: row["baseline_slip_days"]
            for row in dashboard["charts"][3]["data_table"]
        }
        self.assertEqual(slips["Project One P6"], 361)

    def test_project_comparison_preserves_mapping_facts_without_p6(self):
        self.db.add(models.ProjectMapping(
            project_id="P-2",
            project="Project Two",
            project_name_from_p6="Project Two PSS-05 (39 Loc.)",
            cluster="Wind",
            capacity_mwac=202.8,
        ))
        mapping = self.db.query(models.ProjectMapping).filter_by(project_id="P-1").one()
        mapping.project_name_from_p6 = "Project One PSS-08 (05 Loc.)"
        mapping.cluster = "Wind"
        mapping.capacity_mwac = 26.0
        self.db.commit()

        data = ChartSpecService.project_comparison(self.db, ["P-1", "P-2"])

        self.assertEqual(len(data["projects"]), 2)
        self.assertEqual(data["projects"][0]["capacity_mwac"], 26.0)
        self.assertEqual(data["projects"][0]["location_count"], 5)
        self.assertFalse(data["projects"][0]["p6_available"])
        self.assertIsNone(data["projects"][0]["progress_pct"])
        self.assertEqual(data["projects"][1]["capacity_mwac"], 202.8)

        dashboard, confirmation = build_chart_result(self.db, {
            "chart_type": "project_comparison",
            "project_ids": ["P-1", "P-2"],
        })
        self.assertEqual(len(dashboard["charts"]), 1)
        self.assertEqual(
            dashboard["charts"][0]["chart_type"],
            "project_capacity_comparison",
        )
        self.assertEqual(
            dashboard["charts"][0]["data_table"][1]["location_count"],
            39,
        )
        self.assertIn('"capacity_mwac": 202.8', confirmation)
        self.assertIn('"p6_available": false', confirmation)

    def test_daily_trend_and_block_snapshot_use_grounded_p6_events(self):
        self.db.add(models.P6Project(
            p6_object_id=11,
            project_id="P-1",
            name="Project One",
            data_date=datetime(2026, 8, 1),
        ))
        self.db.add(models.P6WBSNode(
            p6_object_id=101,
            project_object_id=11,
            wbs_name="BLOCK-01",
        ))
        self.db.add_all([
            models.P6Activity(
                p6_object_id=1001,
                project_object_id=11,
                wbs_object_id=101,
                activity_id="A-1",
                name="Foundation",
                status="Completed",
                percent_complete=1,
                actual_finish_date=datetime(2026, 7, 31),
            ),
            models.P6Activity(
                p6_object_id=1002,
                project_object_id=11,
                wbs_object_id=101,
                activity_id="A-2",
                name="MMS",
                status="In Progress",
                percent_complete=0.5,
            ),
        ])
        self.db.commit()

        trend = build_chart(
            self.db, "daily_completion_trend", project_id="P-1", days=7
        )
        blocks = build_chart(self.db, "block_progress", project_id="P-1")

        self.assertEqual(trend["schema_version"], "visualization.v1")
        self.assertEqual(trend["visualization_spec"]["shape"], "combo")
        self.assertTrue(trend["visualization_spec"]["spec_hash"].startswith("sha256:"))
        self.assertEqual(trend["data_table"][-2]["completed_activities"], 1)
        self.assertEqual(blocks["data_table"][0]["block"], "BLOCK-01")
        self.assertEqual(blocks["visualization_spec"]["shape"], "horizontal_bar")
        self.assertEqual(blocks["data_table"][0]["current_activity_completion_pct"], 75.0)
        self.assertTrue(trend["option"]["aria"]["enabled"])

    def test_project_overview_returns_coordinated_executive_bundle(self):
        self.db.add(models.P6Project(
            p6_object_id=31,
            project_id="P-1",
            name="Project One",
            duration_percent_complete=0.72,
            data_date=datetime(2026, 8, 1),
        ))
        self.db.add(models.P6WBSNode(
            p6_object_id=301,
            project_object_id=31,
            wbs_name="BLOCK-01",
        ))
        self.db.add_all([
            models.P6Activity(
                p6_object_id=3101,
                project_object_id=31,
                wbs_object_id=301,
                activity_id="A-1",
                status="Completed",
                percent_complete=1,
                planned_finish_date=datetime(2026, 7, 20),
                actual_finish_date=datetime(2026, 7, 22),
            ),
            models.P6Activity(
                p6_object_id=3102,
                project_object_id=31,
                wbs_object_id=301,
                activity_id="A-2",
                status="In Progress",
                percent_complete=0.5,
                planned_finish_date=datetime(2026, 8, 15),
            ),
        ])
        self.db.commit()

        dashboard, confirmation = build_chart_result(self.db, {
            "chart_type": "project_overview",
            "project_id": "P-1",
        })

        self.assertEqual(dashboard["schema_version"], "visualization.bundle.v1")
        self.assertEqual(dashboard["chart_type"], "project_overview")
        self.assertEqual(len(dashboard["charts"]), 4)
        self.assertEqual(
            [chart["visualization_spec"]["shape"] for chart in dashboard["charts"]],
            ["radial_progress", "combo", "donut", "horizontal_bar"],
        )
        self.assertTrue(all(
            chart["visualization_spec"]["schema_version"] == "visualization.v1"
            for chart in dashboard["charts"]
        ))
        self.assertIn('"chart_count": 4', confirmation)

    def test_planned_vs_actual_progress_chart_uses_activity_finish_s_curve(self):
        self.db.add(models.P6Project(
            p6_object_id=12,
            project_id="P-1",
            name="Project One",
            data_date=datetime(2026, 3, 31),
        ))
        self.db.add_all([
            models.P6Activity(
                p6_object_id=1201,
                project_object_id=12,
                planned_finish_date=datetime(2026, 1, 31),
                actual_finish_date=datetime(2026, 2, 15),
            ),
            models.P6Activity(
                p6_object_id=1202,
                project_object_id=12,
                planned_finish_date=datetime(2026, 3, 1),
            ),
        ])
        self.db.commit()

        chart = build_chart(
            self.db,
            "planned_vs_actual_progress",
            project_id="P-1",
        )

        self.assertFalse(chart.get("no_data", False))
        self.assertEqual(chart["chart_type"], "planned_vs_actual_progress")
        self.assertEqual(chart["visualization_spec"]["shape"], "combo")
        self.assertEqual(
            [series["name"] for series in chart["visualization_spec"]["series"]],
            ["Planned activity finishes", "Actual activity finishes"],
        )
        self.assertIn("50.0 percentage points behind plan", chart["summary"])

    def test_portfolio_milestone_risk_is_current_month_and_rule_based(self):
        self.db.add(models.P6Project(
            p6_object_id=21,
            project_id="P-1",
            name="Project One",
            data_date=datetime(2026, 8, 10),
        ))
        self.db.add(models.P6Activity(
            p6_object_id=2101,
            project_object_id=21,
            activity_id="MS-1",
            name="Grid Energization",
            type="Finish Milestone",
            status="Not Started",
            finish_date=datetime(2026, 8, 9),
            baseline_finish_date=datetime(2026, 8, 5),
            total_float=-8,
        ))
        self.db.commit()

        result = p6_get_portfolio_milestone_risks(self.db)

        self.assertEqual(result["period"], "current_month")
        self.assertEqual(result["projects_at_risk"], 1)
        self.assertEqual(result["projects"][0]["at_risk_milestones"][0]["activity_id"], "MS-1")


if __name__ == "__main__":
    unittest.main()
