import json
import os
import sys
from pathlib import Path
import unittest
from datetime import datetime


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.agent import execute_tool
from engine.tools.p6_tools import p6_list_all_projects
from engine.tools.p6_tools import p6_get_project_summary
from engine.tools.sap_tools import sap_get_inventory, sap_get_po_summary
from engine.tools.tc_tools import tc_get_project_lines
import models
from tests.dashboard_fixtures import (
    clear_dashboard_tables,
    create_dashboard_session_factory,
    dashboard_summary,
    load_catalog_baseline,
    seed_catalog_scenario,
)


class DashboardChatProjectParityTests(unittest.TestCase):
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
        self.expected = load_catalog_baseline()["expected"]

    def tearDown(self):
        self.db.close()

    def test_dashboard_and_chat_tool_have_identical_project_population(self):
        dashboard_result = dashboard_summary(self.db)
        chat_result = json.loads(execute_tool(self.db, "p6_list_all_projects", {}))

        dashboard_names = {row["project_name"] for row in dashboard_result["projects"]}
        chat_names = {row["project_name"] for row in chat_result["projects"]}
        dashboard_mapping_ids = {row["mapping_id"] for row in dashboard_result["projects"]}
        chat_mapping_ids = {row["mapping_id"] for row in chat_result["projects"]}

        self.assertEqual(dashboard_result["summary"]["total_projects"], chat_result["total_projects"])
        self.assertEqual(dashboard_names, chat_names)
        self.assertEqual(dashboard_mapping_ids, chat_mapping_ids)
        self.assertEqual(chat_result["projects_with_p6_data"], self.expected["projects_with_p6_data"])

    def test_mapping_only_availability_is_preserved(self):
        dashboard_result = dashboard_summary(self.db)
        chat_result = p6_list_all_projects(self.db)
        dashboard_row = next(row for row in dashboard_result["projects"] if row["project_name"] == "Beta Wind 50MW")
        chat_row = next(row for row in chat_result["projects"] if row["project_name"] == "Beta Wind 50MW")

        self.assertIsNone(dashboard_row["p6"]["id"])
        self.assertFalse(chat_row["p6_available"])
        self.assertEqual(chat_row["status"], "P6 data unavailable")

    def test_portfolio_filter_has_dashboard_chat_parity(self):
        dashboard_result = dashboard_summary(self.db, "north+solar")
        chat_result = json.loads(execute_tool(
            self.db,
            "p6_list_all_projects",
            {"portfolio": "north+solar"},
        ))

        self.assertEqual(dashboard_result["summary"]["total_projects"], chat_result["total_projects"])
        self.assertEqual(
            {row["project_name"] for row in dashboard_result["projects"]},
            {row["project_name"] for row in chat_result["projects"]},
        )

    def test_schedule_progress_and_delay_have_dashboard_chat_parity(self):
        p6 = self.db.query(models.P6Project).filter_by(project_id="SOLAR-A").one()
        p6.actual_non_labor_units = 35
        p6.at_completion_non_labor_units = 100
        p6.finish_date_variance = -4
        p6.data_date = datetime(2026, 7, 14)
        self.db.commit()

        dashboard_row = next(
            row for row in dashboard_summary(self.db)["projects"]
            if row["p6"]["id"] == "SOLAR-A"
        )
        chat = p6_get_project_summary(self.db, "SOLAR-A")

        self.assertEqual(dashboard_row["p6"]["progress"], chat["progress_pct"])
        self.assertEqual(dashboard_row["p6"]["health"], chat["schedule_health"])
        self.assertEqual(chat["progress_unit"], "percent")
        self.assertEqual(chat["finish_date_variance_unit"], "days")

    def test_sap_population_and_aggregates_have_dashboard_chat_parity(self):
        uploaded = datetime(2026, 7, 16, 8)
        self.db.add_all([
            models.MTPOAmount(
                purchasing_document="PO-1", wbs_element="WBS-1.CHILD",
                order_quantity=20.5, delivered_qty=8.5, still_to_deliver_qty=12,
                net_order_value_inr=2500000, currency="INR", upload_time=uploaded,
            ),
            models.MTPOAmount(
                purchasing_document="PO-WRONG", wbs_element="WBS-10",
                order_quantity=999, delivered_qty=0, still_to_deliver_qty=999,
                net_order_value_inr=999, currency="INR", upload_time=uploaded,
            ),
            models.MTInventory(
                wbs_element="WBS-1/STORE", quantity_inv=7.5,
                value_unrestricted=1000, base_unit="EA", upload_time=uploaded,
            ),
        ])
        self.db.commit()

        dashboard_row = next(
            row for row in dashboard_summary(self.db)["projects"]
            if row["p6"]["id"] == "SOLAR-A"
        )
        po = sap_get_po_summary(self.db, "SOLAR-A")
        inventory = sap_get_inventory(self.db, "SOLAR-A")

        self.assertEqual(dashboard_row["sap"]["po_qty"], 20.5)
        self.assertEqual(dashboard_row["sap"]["po_qty"], po["summary"]["total_ordered_qty_raw"])
        self.assertEqual(dashboard_row["sap"]["in_transit_qty"], po["summary"]["total_pending_qty_raw"])
        self.assertEqual(dashboard_row["sap"]["inventory_qty"], inventory["total_quantity_raw"])
        self.assertEqual(dashboard_row["sap"]["distinct_po_count"], 1)

    def test_transmission_line_snapshot_has_dashboard_chat_parity(self):
        uploaded = datetime(2026, 7, 17, 9)
        self.db.add_all([
            models.TcNetworkEdge(
                region="khavda", edge_id="LINE-1", mapping_id=1,
                from_label="A", to_label="B", status="In Progress",
                normalized_status="in_progress", foundation="50%",
                erection="25%", stringing="0%", is_delayed=True,
                upload_time=uploaded,
            ),
            models.TcNetworkEdge(
                region="Khavda", edge_id="LINE-1", mapping_id=1,
                from_label="OLD", to_label="OLD", status="Not Started",
                normalized_status="not_started", foundation="0%",
                erection="0%", stringing="0%", is_delayed=False,
                upload_time=datetime(2026, 7, 1),
            ),
        ])
        self.db.commit()

        dashboard_row = next(
            row for row in dashboard_summary(self.db)["projects"]
            if row["p6"]["id"] == "SOLAR-A"
        )
        chat = tc_get_project_lines(self.db, "SOLAR-A")

        self.assertEqual(len(dashboard_row["tc"]["data"]["khavda"]), chat["total_lines"])
        self.assertEqual(dashboard_row["tc"]["data"]["khavda"][0]["status"], chat["lines"][0]["status"])
        self.assertEqual(chat["lines"][0]["edge_id"], "LINE-1")


if __name__ == "__main__":
    unittest.main()
