import os
import sys
import unittest
from datetime import datetime
from pathlib import Path


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
import models
from services import transmission_service as service
from services import project_service
from services.sap_project_data_service import get_sap_project_data
from routers import projects


class TransmissionServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://")
        Base.metadata.create_all(bind=cls.engine)
        cls.Session = sessionmaker(bind=cls.engine)

    def setUp(self):
        self.db = self.Session()
        for table in reversed(Base.metadata.sorted_tables):
            self.db.execute(table.delete())
        self.db.add_all([
            models.ProjectMapping(id=1, project_id="P-1", project="Project One"),
            models.ProjectMapping(id=2, project_id="P-2", project="Project Two"),
            models.TcProjectEntry(
                id=1,
                region="KHAVDA",
                mapping_id=1,
                block="B-1",
                phase="['Phase A']",
                kps="1",
                upload_time=datetime(2026, 7, 10),
            ),
            # Historical duplicate for the same direct association.
            self.edge(1, " Khavda ", "SHARED", 1, datetime(2026, 7, 1), "Old", "KPS-I", "PSS"),
            self.edge(2, "khavda", "SHARED", 1, datetime(2026, 7, 12), "Mapped", "KPS-I", "PSS"),
            # Same physical line from a second mapping. Phase association puts it in the union,
            # and its newer snapshot must win physical deduplication.
            self.edge(
                3,
                "KHAVDA",
                " shared ",
                2,
                datetime(2026, 7, 14),
                "Physical latest",
                "KPS-I",
                "PSS",
                "{'projects': ['Other'], 'phases': ['phase a']}",
            ),
            self.edge(
                4,
                "Khavda",
                "PHASE-LINE",
                2,
                datetime(2026, 7, 13),
                "In Progress",
                "KPS-I yard",
                "Remote",
                '{"phases": ["Phase A"], "projects": ["Solar A"]}',
                foundation="25%",
                erection="50",
                stringing="0%",
                expected_date="2027-03-15",
                scd="Jan-27",
                is_delayed=True,
            ),
            # Phase matches, but KPS filtering applies after the complete direct/phase union.
            self.edge(
                5,
                "Khavda",
                "WRONG-KPS",
                2,
                datetime(2026, 7, 15),
                "In Progress",
                "Remote A",
                "Remote B",
                "Phase A",
            ),
        ])
        self.db.commit()

    @staticmethod
    def edge(
        row_id,
        region,
        edge_id,
        mapping_id,
        uploaded,
        status,
        from_label,
        to_label,
        projects=None,
        **values,
    ):
        return models.TcNetworkEdge(
            id=row_id,
            region=region,
            edge_id=edge_id,
            mapping_id=mapping_id,
            upload_time=uploaded,
            status=status,
            from_label=from_label,
            to_label=to_label,
            projects=projects,
            **values,
        )

    def tearDown(self):
        self.db.close()

    def test_latest_selection_normalizes_region_and_is_deterministic(self):
        physical = service.latest_physical_edges(self.db, "  kHaVdA ")

        self.assertEqual([edge.edge_id.strip() for edge in physical], ["PHASE-LINE", "shared", "WRONG-KPS"])
        self.assertEqual(next(edge for edge in physical if edge.edge_id.strip() == "shared").id, 3)

        same_time = datetime(2026, 7, 20)
        self.db.add_all([
            self.edge(10, "Rajasthan", "R-1", 1, same_time, "Older id", "A", "B"),
            self.edge(11, " rajasthan ", "r-1", 1, same_time, "Newer id", "A", "B"),
        ])
        self.db.commit()
        selected = service.latest_physical_edges(self.db, "RAJASTHAN")
        self.assertEqual([edge.id for edge in selected], [11])

    def test_project_union_phase_kps_and_physical_dedup(self):
        mapping, entries, edges = service.project_edges(self.db, "P-1")

        self.assertEqual(mapping.id, 1)
        self.assertEqual(len(entries), 1)
        self.assertEqual([edge.edge_id.strip() for edge in edges], ["PHASE-LINE", "shared"])
        self.assertEqual(next(edge for edge in edges if edge.edge_id.strip() == "shared").id, 3)

    def test_association_parser_accepts_json_literals_lists_and_plain_values(self):
        self.assertEqual(
            service.parse_projects_phases('{"projects": ["A"], "phases": ["I"]}'),
            {"projects": ["A"], "phases": ["I"]},
        )
        self.assertEqual(
            service.parse_projects_phases("{'project': 'B', 'phase': ('II', 'III')}"),
            {"projects": ["B"], "phases": ["II", "III"]},
        )
        self.assertEqual(service.parse_projects_phases('["A", "B"]')["projects"], ["A", "B"])
        self.assertEqual(service.parse_projects_phases("Phase A")["phases"], ["Phase A"])

    def test_canonical_dto_and_freshness(self):
        edge = next(edge for edge in service.latest_physical_edges(self.db) if edge.edge_id == "PHASE-LINE")
        dto = service.edge_dict(edge)

        self.assertEqual(dto["region"], "Khavda")
        self.assertEqual(dto["canonical_status"], "in_progress")
        self.assertEqual(dto["avg_progress"], 25.0)
        self.assertEqual(dto["expected_date_iso"], "2027-03-15")
        self.assertEqual(dto["scd_iso"], "2027-01-01")
        self.assertEqual(dto["days_delayed"], 73)
        self.assertEqual(service.freshness(self.db, " khavda "), {
            "synced_at": "2026-07-15T00:00:00",
            "exists": True,
            "region": "Khavda",
        })

        status = service.project_status(self.db, "P-1")
        self.assertEqual(status["readiness_status"], "At Risk")
        self.assertEqual(status["readiness_pct"], 0.0)
        self.assertEqual(
            status["readiness_formula"],
            "completed physical lines / total physical lines",
        )

    def test_negative_status_precedes_completion_and_progress(self):
        edge = self.edge(
            20, "Khavda", "NEGATIVE", 1, datetime(2026, 7, 20),
            "Delayed - commissioning complete", "A", "B", foundation="100%",
        )
        self.assertEqual(service.canonical_status(edge), "delayed")

    def test_project_uses_every_mapping_row_for_project_id(self):
        self.db.add(models.ProjectMapping(id=3, project_id="P-1", project="Project One Alias"))
        self.db.add(self.edge(
            21, "Rajasthan", "SECOND-MAPPING", 3, datetime(2026, 7, 20),
            "Not Started", "KPS-I", "B",
        ))
        self.db.commit()

        _, _, edges = service.project_edges(self.db, "P-1")

        self.assertIn("SECOND-MAPPING", [edge.edge_id for edge in edges])

        route = projects.get_project_tc_network("P-1", db=self.db)
        self.assertIn("SECOND-MAPPING", [edge["id"] for edge in route["edges"]])
        self.assertEqual(route["metadata"]["entry_count"], 1)

    def test_project360_detail_uses_shared_sap_totals_and_po_contract(self):
        mapping = self.db.query(models.ProjectMapping).filter_by(id=1).one()
        mapping.spv_plant_code = "PLANT"
        mapping.capacity_mwac = 100
        mapping.cluster = "Solar"
        self.db.add(models.P6Project(
            p6_object_id=30, project_id="P-1", name="Project One",
            duration_percent_complete=0.5,
        ))
        self.db.add_all([
            models.P6Activity(
                p6_object_id=301,
                project_object_id=30,
                name="Block-01 COD",
                status="Completed",
                type="Task Dependent",
                wbs_name="CONSTRUCTION-COMMISSIONING",
                planned_finish_date=datetime(2026, 7, 5),
                actual_finish_date=datetime(2026, 7, 4),
            ),
            models.MTPOAmount(
                purchasing_document="PO-1", plant_code="PLANT", vendor_name="Vendor",
                order_quantity=4, still_to_deliver_qty=2, net_order_value_inr=40,
                delivered_value_inr_cr=0.000001,
            ),
            models.MTPOAmount(
                purchasing_document="PO-1", plant_code="PLANT", vendor_name="Vendor",
                order_quantity=6, still_to_deliver_qty=3, net_order_value_inr=60,
                delivered_value_inr_cr=0.000002,
            ),
            models.MTInventory(plant_code="PLANT", quantity_inv=3, value_unrestricted=30),
        ])
        self.db.commit()

        shared = get_sap_project_data(self.db, "P-1")
        detail = project_service.get_project_360_detail(self.db, "P-1")
        project_summary = next(
            row
            for row in project_service.calculate_project_360_metrics(self.db)
            if row["projectId"] == "P-1"
        )
        summary = detail["sap"]["summary"]

        self.assertEqual(summary["totalOrderedQty"], shared["totals"]["purchase_orders"]["ordered_quantity"])
        self.assertEqual(summary["totalBudgetINR"], shared["totals"]["purchase_orders"]["order_value"])
        self.assertEqual(summary["totalInventoryQty"], shared["totals"]["inventory"]["quantity"])
        self.assertEqual(summary["totalPOs"], 1)
        self.assertEqual(summary["totalPORows"], 2)
        self.assertEqual(detail["sap"]["vendorBreakdown"][0]["poCount"], 1)
        self.assertEqual(detail["mapping"]["capacityMW"], 100)
        self.assertEqual(detail["mapping"]["mwGenerated"], 12.5)
        self.assertEqual(detail["mapping"]["codBlocksDone"], 1)
        self.assertEqual(detail["mapping"]["pendingCodBlocks"], 7)
        self.assertEqual(detail["mapping"]["blocksStatus"]["BLOCK-1"], {
            "cod": "Completed",
            "tr": "Not Started",
            "cod_forecast_date": "2026-07-05",
            "cod_actual_date": "2026-07-04",
            "tr_actual_date": None,
        })
        self.assertEqual(
            detail["mapping"]["capacityMetadata"]["formula"]["version"],
            "dashboard-capacity-overview-v1",
        )
        self.assertEqual(project_summary["capacityMW"], 100)
        self.assertEqual(project_summary["codMW"], 12.5)
        self.assertEqual(project_summary["codBlocksDone"], 1)


if __name__ == "__main__":
    unittest.main()
