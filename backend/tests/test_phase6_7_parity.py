import json
import os
import sys
from datetime import datetime
from pathlib import Path
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models
from engine.agent import execute_tool
from routers.dashboard import get_capacity_overview
from routers.quality import get_quality_overview
from routers.risk import get_command_center
from services.project_service import calculate_project_360_metrics
from tests.dashboard_fixtures import (
    clear_dashboard_tables,
    create_dashboard_session_factory,
    seed_catalog_scenario,
)


class PhaseSixSevenParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, cls.Session = create_dashboard_session_factory()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.db = self.Session()
        clear_dashboard_tables(self.db)
        seed_catalog_scenario(self.db)

    def tearDown(self):
        self.db.close()

    def test_capacity_route_and_chat_tool_share_project_facts(self):
        self.db.add(models.P6Activity(
            p6_object_id=1001,
            activity_id="COD-1",
            project_object_id=101,
            name="COD Block-01",
            status="Completed",
            type="Task Dependent",
            wbs_name="Construction and Commissioning",
            actual_finish_date=datetime(2026, 4, 1),
            last_synced_at=datetime(2026, 4, 2),
        ))
        self.db.commit()

        route = get_capacity_overview(db=self.db)
        chat = json.loads(execute_tool(
            self.db,
            "capacity_get_project_status",
            {"project_id": "SOLAR-A"},
        ))
        route_project = next(row for row in route["projects"] if row["project_id"] == "SOLAR-A")
        chat_project = chat["projects"][0]

        self.assertEqual(route_project["cod_mw"], chat_project["cod_mw"])
        self.assertEqual(route_project["tr_mw"], chat_project["tr_mw"])
        self.assertEqual(route_project["remaining_capacity"], chat_project["remaining_capacity"])
        self.assertEqual(route["metadata"]["formula"], chat["metadata"]["formula"])

    def test_quality_route_and_chat_tool_share_normalized_facts(self):
        self.db.add_all([
            models.PulseNC(
                pulse_id="NC-1",
                project_name="Alpha Solar 100MW",
                status="Completed",
                category="critical",
                created_at=datetime(2026, 7, 1),
                approved_at=datetime(2026, 7, 3),
                last_synced_at=datetime(2026, 7, 4),
            ),
            models.PulseRFI(
                pulse_id="RFI-1",
                project_name="Alpha Solar 100MW",
                status="Raised",
                last_synced_at=datetime(2026, 7, 4),
            ),
        ])
        self.db.commit()

        route = get_quality_overview(db=self.db)
        chat = json.loads(execute_tool(self.db, "quality_get_portfolio_overview", {}))

        for field in ("total_ncs", "open_ncs", "closure_rate", "total_rfis", "open_rfis"):
            self.assertEqual(route[field], chat[field])
        self.assertEqual(
            json.loads(json.dumps(route["provenance"])),
            chat["provenance"],
        )

    def test_named_risk_route_and_chat_tool_share_metric_envelope(self):
        project = self.db.query(models.P6Project).filter_by(project_id="SOLAR-A").one()
        project.finish_date_variance = -45
        self.db.commit()

        route = get_command_center(db=self.db)
        chat = json.loads(execute_tool(
            self.db,
            "risk_get_metric",
            {"metric_id": "command_center.schedule_risk_count"},
        ))
        route_metric = route["metrics"]["command_center.schedule_risk_count"]

        self.assertEqual(route_metric, chat)
        self.assertEqual(chat["value"], 1)
        self.assertFalse(chat["heuristic"])

    def test_project360_and_chat_share_named_status_tier_inputs(self):
        project = self.db.query(models.P6Project).filter_by(project_id="SOLAR-A").one()
        project.finish_date_variance = -12
        project.duration_percent_complete = 0.4
        self.db.add(models.MTPOAmount(
            purchasing_document="PO-RISK",
            wbs_element="WBS-1",
            order_quantity=100,
            still_to_deliver_qty=20,
        ))
        self.db.add(models.MTInventory(
            wbs_element="WBS-1",
            quantity_inv=30,
        ))
        self.db.commit()

        dashboard_project = next(
            row for row in calculate_project_360_metrics(self.db)
            if row["projectId"] == "SOLAR-A"
        )
        chat = json.loads(execute_tool(
            self.db,
            "risk_get_metric",
            {
                "metric_id": "project360.status_tier",
                "project_id": "SOLAR-A",
            },
        ))

        self.assertEqual(dashboard_project["statusTier"], chat["value"])
        self.assertEqual(
            dashboard_project["namedRiskMetrics"]["project360.status_tier"],
            chat,
        )

    def test_project360_tabs_and_chat_share_portfolio_tier_counts(self):
        dashboard = calculate_project_360_metrics(self.db)
        expected = {
            tier: sum(project["statusTier"] == tier for project in dashboard)
            for tier in ("Critical", "High Risk", "Watchlist", "Healthy", "Completed")
        }
        chat = json.loads(execute_tool(
            self.db,
            "risk_get_metric",
            {"metric_id": "project360.status_tier_counts"},
        ))

        self.assertEqual(chat["value"], expected)
        self.assertEqual(chat["components"]["projects_evaluated"], len(dashboard))
        self.assertEqual(sum(chat["value"].values()), len(dashboard))


if __name__ == "__main__":
    unittest.main()
