import os
import sys
from datetime import datetime
from pathlib import Path
import unittest

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import models
from engine.tools.sap_tools import sap_get_consumption, sap_get_po_summary
from services.sap_project_data_service import get_sap_project_data, get_sap_projects_data


TABLES = [
    models.ProjectMapping.__table__,
    models.MTPOAmount.__table__,
    models.MTInventory.__table__,
    models.MTMaterialDocument.__table__,
]


class SapProjectDataServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        models.Base.metadata.create_all(cls.engine, tables=TABLES)
        cls.Session = sessionmaker(bind=cls.engine)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()

    def setUp(self):
        self.db = self.Session()
        for table in reversed(TABLES):
            self.db.execute(table.delete())
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def mapping(self, project_id, *, wbs=None, spv=None, agel=None, capacity=100):
        row = models.ProjectMapping(
            project_id=project_id,
            project=project_id,
            project_name_from_p6=f"Project {project_id}",
            module_wbs=wbs,
            spv_plant_code=spv,
            agel=agel,
            capacity_mwac=capacity,
        )
        self.db.add(row)
        return row

    def po(self, wbs, plant, document, quantity, *, upload_hour=1):
        row = models.MTPOAmount(
            wbs_element=wbs,
            plant_code=plant,
            purchasing_document=document,
            order_quantity=quantity,
            delivered_qty=quantity / 2,
            still_to_deliver_qty=quantity / 2,
            net_order_value_inr=quantity * 10,
            currency="INR",
            upload_time=datetime(2026, 7, 1, upload_hour),
        )
        self.db.add(row)
        return row

    def test_wbs_is_bounded_and_never_falls_back_to_plant(self):
        self.mapping("P1", wbs="ROOT-01", spv="PLANT")
        exact = self.po("ROOT-01", "OTHER", "PO-1", 1)
        child = self.po("ROOT-01/CHILD", "OTHER", "PO-2", 2)
        self.po("ROOT-010", "OTHER", "PO-3", 100)
        self.po("UNRELATED", "PLANT", "PO-4", 1000)
        self.db.commit()

        data = get_sap_project_data(self.db, "P1")

        self.assertEqual(data["scope"]["type"], "wbs")
        self.assertIsNone(data["scope"]["selected_plant"])
        self.assertEqual(data["purchase_orders"], [exact, child])
        self.assertEqual(data["totals"]["purchase_orders"]["ordered_quantity"], 3.0)

        self.mapping("EMPTY", wbs="NO-ROWS", spv="PLANT")
        self.db.commit()
        empty = get_sap_project_data(self.db, "EMPTY")
        self.assertEqual(empty["purchase_orders"], [])
        self.assertEqual(empty["scope"]["type"], "wbs")

    def test_plant_selection_prefers_spv_then_agel_and_allocates_by_capacity(self):
        self.mapping("P1", spv="SHARED", agel="AGEL", capacity=25)
        self.mapping("P2", spv="SHARED", agel="OTHER", capacity=75)
        self.po(None, "SHARED", "PO-1", 40)
        self.po(None, "AGEL", "PO-2", 999)
        self.db.add(models.MTInventory(
            plant_code="SHARED", quantity_inv=20.0, value_unrestricted=200.0,
            base_unit="EA",
        ))
        self.db.commit()

        data = get_sap_project_data(self.db, "P1")

        self.assertEqual(data["scope"]["selected_plant"], "SHARED")
        self.assertEqual(data["scope"]["plant_source"], "spv_plant_code")
        self.assertEqual(data["scope"]["allocation_ratio"], 0.25)
        self.assertEqual(data["totals"]["purchase_orders"]["ordered_quantity"], 10.0)
        self.assertEqual(data["totals"]["inventory"]["quantity"], 5.0)

        self.mapping("P3", spv="EMPTY", agel="AGEL", capacity=50)
        self.mapping("P4", spv="X", agel="AGEL", capacity=50)
        self.db.commit()
        agel = get_sap_project_data(self.db, "P3")
        self.assertEqual(agel["scope"]["selected_plant"], "AGEL")
        self.assertEqual(agel["scope"]["plant_source"], "agel")
        self.assertEqual(agel["scope"]["allocation_ratio"], 0.4)
        self.assertEqual(agel["totals"]["purchase_orders"]["ordered_quantity"], 399.6)

    def test_fallback_is_selected_independently_for_each_source_table(self):
        self.mapping("P1", spv="SPV", agel="AGEL", capacity=100)
        self.po(None, "SPV", "PO-1", 10)
        self.db.add(models.MTInventory(
            plant_code="AGEL", quantity_inv=7, value_unrestricted=70, base_unit="EA",
        ))
        self.db.commit()

        data = get_sap_project_data(self.db, "P1")

        self.assertEqual(data["scope"]["sources"]["mt_poamount"]["selected_plant"], "SPV")
        self.assertEqual(data["scope"]["sources"]["mt_inventory"]["selected_plant"], "AGEL")
        self.assertEqual(data["totals"]["purchase_orders"]["ordered_quantity"], 10)
        self.assertEqual(data["totals"]["inventory"]["quantity"], 7)

    def test_allocation_excludes_demo_wbs_and_duplicate_project_mappings(self):
        self.mapping("P1", spv="SHARED", capacity=25)
        self.mapping("P1", spv="SHARED", capacity=25)
        self.mapping("P2", spv="SHARED", capacity=75)
        demo = self.mapping("DEMO", spv="SHARED", capacity=900)
        demo.project_name_from_p6 = "Demo Training Project"
        self.mapping("WBS", wbs="ROOT", spv="SHARED", capacity=1000)
        self.po(None, "SHARED", "PO-1", 100)
        self.db.commit()

        data = get_sap_project_data(self.db, "P1")

        self.assertEqual(data["scope"]["allocation_ratio"], 0.25)
        self.assertEqual(data["totals"]["purchase_orders"]["ordered_quantity"], 25)
        self.assertEqual(data["counts"]["po_row_count"], 1)

    def test_bulk_snapshot_query_count_does_not_grow_per_project(self):
        self.mapping("P1", spv="A")
        self.mapping("P2", spv="B")
        self.po(None, "A", "PO-1", 1)
        self.po(None, "B", "PO-2", 2)
        self.db.commit()
        statements = []

        def count_query(*args):
            statements.append(args[2])

        event.listen(self.engine, "before_cursor_execute", count_query)
        try:
            result = get_sap_projects_data(self.db, ["P1", "P2"])
        finally:
            event.remove(self.engine, "before_cursor_execute", count_query)

        self.assertEqual(set(result), {"P1", "P2"})
        self.assertEqual(len(statements), 4)  # catalog plus the three SAP source tables

    def test_counts_are_explicit_and_tool_rounds_only_final_total(self):
        self.mapping("P1", wbs="WBS")
        self.po("WBS", "P", "PO-1", 1.4, upload_hour=1)
        self.po("WBS.CHILD", "P", "PO-1", 1.4, upload_hour=2)
        self.po("WBS-CHILD", "P", "PO-2", 0.2, upload_hour=3)
        self.db.commit()

        data = get_sap_project_data(self.db, "P1")
        summary = sap_get_po_summary(self.db, "P1")

        self.assertEqual(data["counts"]["po_row_count"], 3)
        self.assertEqual(data["counts"]["distinct_po_count"], 2)
        self.assertAlmostEqual(data["totals"]["purchase_orders"]["ordered_quantity"], 3.0)
        self.assertEqual(summary["summary"]["total_po_count"], 3)
        self.assertEqual(summary["summary"]["distinct_po_count"], 2)
        self.assertEqual(summary["summary"]["total_ordered_qty"], 3)
        self.assertEqual(summary["freshness"]["mt_poamount"], "2026-07-01T03:00:00")
        self.assertIn("INR", summary["summary"]["currency"])

    def test_222_and_262_are_reversals(self):
        self.mapping("P1", wbs="WBS")
        for movement, quantity in (("221", 10.25), ("261", -4.25), ("222", -2.5), ("262", 1.5)):
            self.db.add(models.MTMaterialDocument(
                wbs_element="WBS",
                movement_type=movement,
                quantity=quantity,
                amount_in_lc=quantity * 10,
                base_unit="KG",
            ))
        self.db.commit()

        data = get_sap_project_data(self.db, "P1")
        totals = data["totals"]["consumption"]
        tool = sap_get_consumption(self.db, "P1")

        self.assertEqual(totals["issued_quantity"], 14.5)
        self.assertEqual(totals["reversal_quantity"], 4.0)
        self.assertEqual(totals["net_quantity"], 10.5)
        self.assertEqual(tool["issued_qty"], 14)
        self.assertEqual(tool["returned_qty"], 4)
        self.assertEqual(tool["net_consumed"], 10)
        self.assertEqual(tool["quantity_units"], ["KG"])


if __name__ == "__main__":
    unittest.main()
