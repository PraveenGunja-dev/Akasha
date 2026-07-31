import os
import sys
from pathlib import Path
import unittest
from datetime import datetime


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests.dashboard_fixtures import (
    clear_dashboard_tables,
    create_dashboard_session_factory,
    dashboard_summary,
    load_catalog_baseline,
    seed_catalog_scenario,
)
from routers import dashboard, financials, logistics, pmag, projects
from services.project_service import calculate_project_360_metrics
from engine.agent import _authorize_legacy_domain_tool
import models


class DashboardProjectContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine, cls.Session = create_dashboard_session_factory()

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.db = self.Session()
        pmag.clear_pmag_caches()
        clear_dashboard_tables(self.db)
        seed_catalog_scenario(self.db)
        self.expected = load_catalog_baseline()["expected"]

    def tearDown(self):
        pmag.clear_pmag_caches()
        self.db.close()

    def test_summary_uses_non_demo_mapping_population(self):
        result = dashboard_summary(self.db)
        names = {row["project_name"] for row in result["projects"]}

        self.assertEqual(result["summary"]["total_projects"], self.expected["total_projects"])
        self.assertEqual(result["summary"]["total_projects"], len(result["projects"]))
        self.assertEqual(names, set(self.expected["all_project_names"]))
        self.assertNotIn("Demo Training Project", names)
        self.assertNotIn("Unmapped P6 Project", names)

    def test_summary_keeps_mapping_only_project_without_p6_identity(self):
        result = dashboard_summary(self.db)
        mapped_only = next(row for row in result["projects"] if row["project_name"] == "Beta Wind 50MW")

        self.assertIsNone(mapped_only["p6"]["id"])
        self.assertEqual(mapped_only["p6"]["progress"], 0)
        self.assertEqual(mapped_only["p6"]["health"], "On Track")
        self.assertEqual(
            result["summary"]["on_track_projects"],
            sum(project["p6"]["health"] == "On Track" for project in result["projects"]),
        )

    def test_null_project_id_mapping_remains_available_without_crashing_sap_consumers(self):
        self.db.add(models.ProjectMapping(
            id=20,
            project_id=None,
            project="Mapping Only Solar",
            project_name_from_p6="Mapping Only Solar",
            cluster="North Solar",
            category="Solar",
            capacity_mwac=25,
            module_wbs="MAP-ONLY",
        ))
        self.db.add(models.MTPOAmount(
            purchasing_document="PO-MAP",
            wbs_element="MAP-ONLY.CHILD",
            order_quantity=5,
        ))
        self.db.commit()

        summary = dashboard_summary(self.db)
        project = next(row for row in summary["projects"] if row["mapping_id"] == 20)
        project360 = next(
            row for row in calculate_project_360_metrics(self.db)
            if row["projectName"] == "Mapping Only Solar"
        )

        self.assertEqual(project["sap"]["po_qty"], 5)
        self.assertEqual(project360["orderedQty"], 5)

    def test_legacy_domain_tools_enforce_selected_project_scope(self):
        _authorize_legacy_domain_tool(
            self.db,
            "p6_get_project_summary",
            {"project_id": "SOLAR-A"},
            ["SOLAR-A"],
        )
        with self.assertRaises(PermissionError):
            _authorize_legacy_domain_tool(
                self.db,
                "p6_get_project_summary",
                {"project_id": "WIND-B"},
                ["SOLAR-A"],
            )
        with self.assertRaises(PermissionError):
            _authorize_legacy_domain_tool(
                self.db,
                "capacity_get_portfolio_overview",
                {},
                ["SOLAR-A"],
            )
        for tool_name in ("portfolio_get_notifications", "render_chart"):
            with self.assertRaises(PermissionError):
                _authorize_legacy_domain_tool(
                    self.db,
                    tool_name,
                    {},
                    ["SOLAR-A"],
                )

    def test_summary_uses_tokenized_portfolio_filter(self):
        spaced = dashboard_summary(self.db, "north solar")
        plus = dashboard_summary(self.db, "north+solar")

        expected_ids = set(self.expected["north_solar_project_ids"])
        self.assertEqual({row["p6"]["id"] for row in spaced["projects"]}, expected_ids)
        self.assertEqual({row["p6"]["id"] for row in plus["projects"]}, expected_ids)

    def test_all_portfolios_sentinel_matches_unfiltered_population(self):
        unfiltered = dashboard_summary(self.db)
        all_portfolios = dashboard_summary(self.db, "All Portfolios")

        self.assertEqual(unfiltered["summary"]["total_projects"], all_portfolios["summary"]["total_projects"])

    def test_p6_summary_is_limited_to_catalog_projects(self):
        projects.clear_project_caches()
        result = projects.get_project_summary(nocache=True, db=self.db)
        projects.clear_project_caches()

        self.assertEqual([row["project_id"] for row in result], ["SOLAR-A"])

    def test_quality_contractor_enrichment_uses_catalog_population(self):
        self.db.add(models.PulseNC(
            pulse_id="NC-1",
            status="raised",
            project_name="Alpha Solar 100MW",
            vendor_name="Synthetic Vendor",
        ))
        self.db.commit()

        result = dashboard_summary(self.db)
        contractor = result["summary"]["quality"]["top_contractors"][0]

        self.assertEqual(contractor["name"], "Synthetic Vendor")
        self.assertEqual(contractor["projects"][0]["mapping_id"], 1)

    def test_quality_summary_uses_canonical_metrics_associations_and_freshness(self):
        synced = datetime(2026, 7, 20, 9)
        self.db.add_all([
            models.PulseNC(
                pulse_id="NC-OPEN", status="RAISED", project_id="SOLAR-A",
                project_name="Source Name Does Not Match", vendor_name="Vendor One",
                last_synced_at=synced,
            ),
            models.PulseNC(
                pulse_id="NC-DONE", status="COMPLETED", project_id="SOLAR-A",
                project_name="Source Name Does Not Match", vendor_name="vendor one",
                last_synced_at=synced,
            ),
            models.PulseRFI(
                pulse_id="RFI-DONE", status="COMPLETED", project_id="SOLAR-A",
                last_synced_at=synced,
            ),
        ])
        self.db.commit()

        quality = dashboard_summary(self.db)["summary"]["quality"]

        self.assertEqual(
            {key: quality[key] for key in (
                "total_ncs", "open_ncs", "resolved_ncs", "closure_rate",
                "total_rfis", "completed_rfis",
            )},
            {
                "total_ncs": 2, "open_ncs": 1, "resolved_ncs": 1,
                "closure_rate": 50.0, "total_rfis": 1, "completed_rfis": 1,
            },
        )
        self.assertEqual(quality["top_contractors"], [{
            "name": "Vendor One",
            "value": 1,
            "projects": [{
                "project_name": "Alpha Solar 100MW",
                "p6_name": "Alpha Solar 100MW",
                "mapping_id": 1,
                "p6_id": "SOLAR-A",
                "open_ncs": 1,
            }],
        }])
        self.assertEqual(quality["freshness"]["data_as_of"], synced.isoformat())
        self.assertEqual(quality["warnings"], [])

    def test_quality_summary_warns_instead_of_rematching_unassociated_rows(self):
        self.db.add(models.PulseNC(
            pulse_id="NC-UNKNOWN", status="raised", project_name="Missing Project",
            vendor_name="Unmapped Vendor",
        ))
        self.db.commit()

        quality = dashboard_summary(self.db)["summary"]["quality"]

        self.assertEqual(quality["top_contractors"][0]["projects"], [])
        self.assertEqual(quality["warnings"][0]["reason"], "unmatched_project")

    def test_legacy_project_details_use_shared_sap_and_transmission_selection(self):
        newer = datetime(2026, 7, 20)
        self.db.add_all([
            models.MTPOAmount(
                purchasing_document="PO-IN", plant_code="PLANT-1", wbs_element="WBS-1.CHILD",
                order_quantity=12, still_to_deliver_qty=4,
            ),
            models.MTPOAmount(
                purchasing_document="PO-OUT", plant_code="PLANT-1", wbs_element="WBS-10",
                order_quantity=999, still_to_deliver_qty=999,
            ),
            models.MTInventory(wbs_element="WBS-1/STORE", quantity_inv=7),
            models.MTInventory(wbs_element="WBS-10", quantity_inv=999),
            models.TcProjectEntry(
                mapping_id=1, region="Khavda", block="Block 1", phase='{"phases":["Phase A"]}',
            ),
            models.TcNetworkEdge(
                region="khavda", edge_id="DIRECT", mapping_id=1, status="Old",
                upload_time=datetime(2026, 7, 1),
            ),
            models.TcNetworkEdge(
                region="Khavda", edge_id="DIRECT", mapping_id=1, status="Latest",
                upload_time=newer,
            ),
            models.TcNetworkEdge(
                region="Rajasthan", edge_id="PHASE", projects='{"phases":["Phase A"]}',
                status="Phase Associated", upload_time=newer,
            ),
        ])
        self.db.commit()

        result = dashboard.get_project_details(1, db=self.db)

        self.assertEqual(result["sap"]["po_summary"], 12)
        self.assertEqual(result["sap"]["inventory_summary"], 7)
        self.assertEqual([row.purchasing_document for row in result["sap"]["po"]], ["PO-IN"])
        self.assertEqual([row.purchasing_document for row in result["sap"]["in_transit"]], ["PO-IN"])
        self.assertEqual([edge["status"] for edge in result["tc"]["khavda_edges"]], ["Latest"])
        self.assertEqual([edge["status"] for edge in result["tc"]["rajasthan_edges"]], ["Phase Associated"])

    def test_knowledge_graph_serializes_canonical_domain_outputs(self):
        p6 = self.db.query(models.P6Project).filter_by(project_id="SOLAR-A").one()
        p6.actual_non_labor_units = 45
        p6.at_completion_non_labor_units = 100
        p6.finish_date_variance = -3
        p6.parent_eps_name = "Solar EPS"
        mapping_only = self.db.query(models.ProjectMapping).filter_by(project_id="WIND-B").one()
        mapping_only.capacity_mwac = 0
        self.db.add_all([
            models.P6Activity(
                p6_object_id=101, project_object_id=p6.p6_object_id,
                activity_id="A-1", status="In Progress",
            ),
            models.MTPOAmount(
                purchasing_document="PO-GRAPH", wbs_element="WBS-1.CHILD",
                order_quantity=12, still_to_deliver_qty=4,
                mw_multiplication_factor=0.5, po_quantities_mw=12.5,
                net_order_value_inr=3000000, vendor_code="V-1",
                vendor_name="100 Canonical Vendor",
            ),
            models.MTInventory(
                wbs_element="WBS-1/STORE", quantity_inv=7, quantity_mw=6.5,
            ),
            models.TcNetworkEdge(
                region="Khavda", edge_id="GRAPH-LINE", mapping_id=1,
                from_label="A", to_label="B", status="Charged",
                normalized_status="charged", is_delayed=False,
            ),
        ])
        self.db.commit()
        dashboard.clear_dashboard_caches()

        result = dashboard.get_knowledge_graph(nocache=True, db=self.db)
        project_nodes = {node["project_id"]: node for node in result["nodes"] if node["category"] in (3, 4)}
        solar = project_nodes["SOLAR-A"]

        self.assertEqual(set(project_nodes), {"SOLAR-A", "WIND-B"})
        self.assertEqual((solar["health"], solar["progress"]), ("delayed", 45))
        self.assertEqual(solar["p6"]["eps_name"], "Solar EPS")
        self.assertEqual(solar["sap"]["po_count"], 1)
        self.assertEqual(solar["sap"]["po_total_cr"], 0.3)
        self.assertEqual(solar["sap"]["po_mw"], 12.5)
        self.assertEqual(solar["sap"]["inventory_mw"], 6.5)
        self.assertEqual(solar["sap"]["in_transit_mw"], 2.0)
        self.assertEqual(solar["sap"]["top_vendors"][0]["name"], "Canonical Vendor")
        self.assertEqual(solar["tc"]["charged_lines"], 1)
        self.assertEqual(solar["tc"]["lines"][0]["name"], "A \u2192 B")
        self.assertEqual(project_nodes["WIND-B"]["capacity"], 50.0)
        self.assertTrue(any(node["category"] == 5 and node["name"] == "Canonical Vendor" for node in result["nodes"]))

    def test_pmag_retains_duration_progress_and_grey_is_not_delayed(self):
        p6 = self.db.query(models.P6Project).filter_by(project_id="SOLAR-A").one()
        p6.duration_percent_complete = 0.25
        p6.actual_non_labor_units = 80
        p6.at_completion_non_labor_units = 100
        p6.finish_date_variance = None
        self.db.commit()

        result = pmag.get_pmag_dashboard(db=self.db)
        row = next(item for item in result["project_health"] if item["project_id"] == "SOLAR-A")

        self.assertEqual(row["pct_complete"], 25.0)
        self.assertEqual(row["overview_progress_pct"], 80.0)
        self.assertEqual(row["rag"], "grey")
        self.assertEqual(result["summary"]["delayed"], 0)

    def test_scoped_sap_totals_deduplicate_project_mappings_and_global_financials_stay_raw(self):
        original = self.db.query(models.ProjectMapping).filter_by(project_id="SOLAR-A").one()
        self.db.add(models.ProjectMapping(
            project_id="SOLAR-A", project=original.project,
            project_name_from_p6=original.project_name_from_p6,
            cluster=original.cluster, category=original.category,
            module_wbs=original.module_wbs, capacity_mwac=original.capacity_mwac,
        ))
        self.db.add(models.MTPOAmount(
            purchasing_document="PO-1", wbs_element=original.module_wbs,
            order_quantity=10, still_to_deliver_qty=4, net_order_value_inr=20000000,
        ))
        self.db.add(models.MTInventory(wbs_element=original.module_wbs, quantity_inv=3))
        self.db.commit()
        financials.clear_financial_cache()
        logistics.clear_logistics_cache()

        scoped_financial = financials.get_financials(project_name=original.project, nocache=True, db=self.db)
        global_financial = financials.get_financials(nocache=True, db=self.db)
        scoped_logistics = logistics.get_logistics(project_name=original.project, nocache=True, db=self.db)

        self.assertEqual(scoped_financial[0]["actualCapex"], 2.0)
        self.assertEqual(global_financial[0]["actualCapex"], 2.0)
        self.assertEqual([item["count"] for item in scoped_logistics], [3.0, 4.0])


if __name__ == "__main__":
    unittest.main()
