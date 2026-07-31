import os
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from database import Base
import models
from services.capacity_milestone_service import (
    ActivityFact,
    CapacityMilestoneService,
    financial_year,
    get_capacity_overview,
    get_project_capacity_status,
    normalize_block_name,
)


TABLES = (
    models.ProjectMapping.__table__,
    models.P6Project.__table__,
    models.P6Activity.__table__,
)


def mapping(
    mapping_id,
    project_id,
    name,
    cluster="Solar North",
    capacity=25,
    p6_name=None,
    category="Utility",
):
    return models.ProjectMapping(
        id=mapping_id,
        project_id=project_id,
        project=name,
        project_name_from_p6=p6_name,
        cluster=cluster,
        category=category,
        capacity_mwac=capacity,
    )


def p6(object_id, project_id, name, *, data_date=None, synced=None):
    return models.P6Project(
        p6_object_id=object_id,
        project_id=project_id,
        name=name,
        data_date=data_date,
        last_synced_at=synced,
    )


def activity(
    object_id,
    project_object_id,
    name,
    when=None,
    *,
    status="Completed",
    activity_type="Task Dependent",
    wbs="CONSTRUCTION-COMMISSIONING",
    actual_start=None,
    planned_finish=None,
    start=None,
    synced=None,
):
    return models.P6Activity(
        p6_object_id=object_id,
        project_object_id=project_object_id,
        name=name,
        status=status,
        type=activity_type,
        wbs_name=wbs,
        actual_finish_date=when,
        actual_start_date=actual_start,
        planned_finish_date=planned_finish,
        start_date=start,
        last_synced_at=synced,
    )


class CapacityMilestonePureFunctionTests(unittest.TestCase):
    def test_april_financial_year_boundary(self):
        self.assertEqual(financial_year(datetime(2026, 3, 31)), "FY25")
        self.assertEqual(financial_year(datetime(2026, 4, 1)), "FY26")
        self.assertIsNone(financial_year(None))

    def test_block_and_wtg_variants_have_stable_identities(self):
        self.assertEqual(normalize_block_name("COD for Block-01"), "BLOCK-01")
        self.assertEqual(normalize_block_name("COD for block 01"), "BLOCK-01")
        self.assertEqual(normalize_block_name("COD for BLOCK_01"), "BLOCK-01")
        self.assertEqual(normalize_block_name("WTG7 Trial Run Certificate"), "WTG7")
        self.assertEqual(normalize_block_name("WTG-7 Trial Run Certificate"), "WTG7")
        self.assertEqual(normalize_block_name("WTG_7 Trial Run Certificate"), "WTG7")
        self.assertIsNone(normalize_block_name("Project COD"))

    def test_internal_facts_are_immutable(self):
        fact = ActivityFact(1, "10", "Block-1 COD", "Completed", "Task", "Construction", None, None, None, None, None)
        with self.assertRaises(FrozenInstanceError):
            fact.name = "changed"


class CapacityMilestoneServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine, tables=TABLES)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_solar_equal_allocation_cod_precedence_fy_and_independent_trend(self):
        self.db.add(mapping(1, " SOL-1 ", "Mapped Solar", capacity=30, p6_name="Solar P6"))
        self.db.add(p6(100, "SOL-1", "Solar P6", data_date=datetime(2026, 4, 5)))
        self.db.add_all([
            activity(1, 100, "Block-01 Trial Run Certificate", datetime(2026, 1, 10)),
            activity(
                2, 100, "block 01 COD", datetime(2026, 4, 2),
                actual_start=datetime(2026, 4, 1),
                planned_finish=datetime(2026, 4, 4),
            ),
            activity(3, 100, "BLOCK_02 Trail Run Certificate", datetime(2026, 3, 31)),
            activity(4, 100, "Block-03 COD", datetime(2026, 4, 3), status="Not Started"),
            activity(5, 100, "Block-04 COD", datetime(2026, 4, 4), wbs="TESTING & COMMISSIONING"),
            activity(6, 100, "Block-05 COD", datetime(2026, 4, 5), activity_type="Finish Milestone"),
            activity(7, 100, "Project COD", datetime(2026, 4, 6)),
        ])
        self.db.commit()

        result = get_capacity_overview(self.db)
        project = result["projects"][0]

        self.assertEqual(project["type"], "Solar")
        self.assertEqual(project["total_capacity"], 30)
        self.assertEqual(project["total_blocks"], 3)
        self.assertEqual(project["cod_blocks"], 1)
        self.assertEqual(project["cod_mw"], 10)
        self.assertEqual(project["tr_blocks"], 1)
        self.assertEqual(project["tr_mw"], 10)
        self.assertEqual(project["remaining_capacity"], 10)
        self.assertEqual(project["remaining_blocks"], 1)
        block_one_fact = next(
            block for block in project["blocks"] if block["block"] == "BLOCK-01"
        )
        self.assertEqual(block_one_fact["capacity"], 10)
        self.assertEqual(block_one_fact["cod_status"], "Completed")
        self.assertEqual(
            block_one_fact["cod_forecast_date"], "2026-04-04T00:00:00"
        )

        self.assertEqual(result["financial_years"], [
            {"name": "FY25", "solar_cod": 0, "solar_tr": 10, "wind_cod": 0, "wind_tr": 0},
            {"name": "FY26", "solar_cod": 10, "solar_tr": 0, "wind_cod": 0, "wind_tr": 0},
        ])
        self.assertEqual(result["totals"]["solar_cod"], 10)
        self.assertEqual(result["totals"]["solar_tr"], 10)
        trends = {row["name"]: row for row in result["monthly_trends"]}
        self.assertEqual(trends["2026-01"]["Solar Trial Run"], 10)
        self.assertEqual(trends["2026-03"]["Solar Trial Run"], 20)
        self.assertEqual(trends["2026-04"]["Solar COD"], 10)
        self.assertEqual(trends["2026-04"]["Solar Trial Run"], 20)
        self.assertEqual([row["block"] for row in result["recent_milestones"]], [
            "BLOCK-03", "BLOCK-01", "BLOCK-02",
        ])
        block_one = next(row for row in result["recent_milestones"] if row["block"] == "BLOCK-01")
        self.assertEqual(block_one["status"], "COD")
        self.assertEqual(block_one["cod_duration"], 1)
        self.assertEqual(block_one["gap_days"], 81)

    def test_wind_map_default_wbs_rule_and_dynamic_capacity(self):
        self.db.add_all([
            mapping(1, "W-MAP", "Mapped Wind", cluster="Wind", capacity=999),
            mapping(2, "W-DEFAULT", "Default Wind", cluster="Offshore Wind", capacity=50),
            p6(3074, "W-MAP", "Mapped Wind"),
            p6(9999, "W-DEFAULT", "Default Wind"),
            activity(1, 3074, "WTG-01 Trial Run Certificate", datetime(2025, 5, 1), wbs="TESTING & COMMISSIONING"),
            activity(2, 3074, "WTG01 COD", datetime(2025, 6, 1), wbs="TESTING & COMMISSIONING"),
            activity(3, 3074, "WTG_2 COD", datetime(2025, 6, 2), wbs="TESTING"),
            activity(4, 3074, "WTG3 COD", datetime(2025, 6, 3), wbs="CONSTRUCTION"),
            activity(5, 9999, "WTG 9 Trail Run Certificate", datetime(2025, 7, 1), wbs="TESTING"),
        ])
        self.db.commit()

        result = CapacityMilestoneService.get_portfolio_overview(self.db)
        rows = {row["project_id"]: row for row in result["projects"]}

        self.assertEqual(rows["W-MAP"]["total_blocks"], 2)
        self.assertEqual(rows["W-MAP"]["total_capacity"], 10.4)
        self.assertEqual(rows["W-MAP"]["cod_blocks"], 2)
        self.assertEqual(rows["W-MAP"]["cod_mw"], 10.4)
        self.assertEqual(rows["W-MAP"]["tr_mw"], 0)
        self.assertEqual(rows["W-MAP"]["source_facts"]["wind_mw_per_wtg"], 5.2)
        self.assertEqual(rows["W-DEFAULT"]["total_capacity"], 3.3)
        self.assertEqual(rows["W-DEFAULT"]["tr_mw"], 3.3)
        self.assertEqual(result["totals"]["wind_cod"], 10.4)
        self.assertEqual(result["totals"]["wind_tr"], 3.3)

    def test_capacity_name_fallback_date_fallback_and_name_mapping_fallback(self):
        self.db.add(mapping(1, "wrong-id", "Bandha_62.5MW", capacity=0, p6_name="P6 Solar 62.5MW"))
        self.db.add(p6(20, "different-id", "P6 Solar 62.5MW"))
        self.db.add_all([
            activity(1, 20, "Block 1 Trial Run Certificate", actual_start=datetime(2024, 4, 2)),
            activity(2, 20, "Block 2 COD", start=datetime(2024, 4, 3)),
        ])
        self.db.commit()

        project = get_capacity_overview(self.db)["projects"][0]

        self.assertTrue(project["p6_available"])
        self.assertEqual(project["total_capacity"], 62.5)
        self.assertEqual(project["total_blocks"], 5)
        self.assertEqual(project["cod_mw"], 12.5)
        self.assertEqual(project["tr_mw"], 12.5)
        self.assertEqual(project["source_facts"]["name_capacity_fallback_mw"], 62.5)

    def test_mapping_only_project_is_retained_with_null_p6_facts(self):
        self.db.add(mapping(1, "NO-P6", "Mapping Only 40MW", cluster="Wind", capacity=40))
        self.db.commit()

        result = get_capacity_overview(self.db)
        project = result["projects"][0]

        self.assertFalse(project["p6_available"])
        self.assertEqual(project["total_capacity"], 40)
        self.assertEqual(project["remaining_capacity"], 40)
        self.assertIsNone(project["source_facts"]["p6_object_id"])
        self.assertIsNone(project["source_facts"]["eligible_activity_count"])
        self.assertIsNone(project["source_facts"]["parsed_block_count"])
        self.assertIsNone(project["freshness"]["data_as_of"])
        self.assertTrue(project["warnings"])
        self.assertTrue(result["metadata"]["warnings"])

    def test_project_status_and_portfolio_scope_return_compatible_envelope(self):
        self.db.add_all([
            mapping(1, "NORTH", "North Solar", cluster="North Solar", category="Utility"),
            mapping(2, "SOUTH", "South Solar", cluster="South Solar", category="Utility"),
            p6(1, "NORTH", "North Solar"),
            p6(2, "SOUTH", "South Solar"),
            activity(1, 1, "Block-1 COD", datetime(2026, 5, 1)),
            activity(2, 2, "Block-1 COD", datetime(2026, 5, 2)),
        ])
        self.db.commit()

        portfolio = CapacityMilestoneService.get_portfolio_overview(self.db, "north+solar")
        status = get_project_capacity_status(self.db, "SOUTH")

        expected_keys = {"financial_years", "monthly_trends", "recent_milestones", "totals", "projects", "metadata"}
        self.assertEqual(set(portfolio), expected_keys)
        self.assertEqual([row["project_id"] for row in portfolio["projects"]], ["NORTH"])
        self.assertEqual([row["project_id"] for row in status["projects"]], ["SOUTH"])
        self.assertEqual(status["totals"]["solar_cod"], 12.5)

    def test_bulk_snapshot_uses_one_select_and_exposes_evidence_and_freshness(self):
        synced = datetime(2026, 7, 2, 9)
        self.db.add(mapping(1, "P-1", "Solar"))
        self.db.add(p6(1, "P-1", "Solar", data_date=datetime(2026, 7, 1), synced=synced))
        self.db.add(activity(1, 1, "Block-1 COD", datetime(2026, 6, 1), synced=datetime(2026, 7, 3, 9)))
        self.db.commit()
        selects = []

        def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        event.listen(self.engine, "before_cursor_execute", count_selects)
        try:
            result = get_capacity_overview(self.db)
        finally:
            event.remove(self.engine, "before_cursor_execute", count_selects)

        self.assertEqual(len(selects), 1)
        self.assertEqual(result["metadata"]["formula"]["version"], "dashboard-capacity-overview-v1")
        self.assertEqual(result["metadata"]["evidence"], {
            "mapping_count": 1,
            "p6_project_count": 1,
            "eligible_activity_count": 1,
            "parsed_block_count": 1,
        })
        self.assertEqual(result["metadata"]["freshness"]["data_as_of"], "2026-07-01T00:00:00")
        self.assertEqual(result["metadata"]["freshness"]["last_synced_at"], "2026-07-03T09:00:00")

    def test_route_and_tools_are_thin_service_adapters(self):
        expected = {"projects": [{"project_id": "P-1"}]}
        with patch.object(
            CapacityMilestoneService, "get_portfolio_overview", return_value=expected
        ) as portfolio_call:
            from engine.tools.capacity_tools import capacity_get_portfolio_overview
            from routers.dashboard import get_capacity_overview as route_overview

            self.assertIs(route_overview("north", self.db), expected)
            self.assertIs(capacity_get_portfolio_overview(self.db, "south"), expected)
            portfolio_call.assert_any_call(self.db, "north")
            portfolio_call.assert_any_call(self.db, "south")

        with patch.object(
            CapacityMilestoneService, "get_project_status", return_value=expected
        ) as project_call:
            from engine.tools.capacity_tools import capacity_get_project_status

            self.assertIs(
                capacity_get_project_status(self.db, "P-1", "north"), expected
            )
            project_call.assert_called_once_with(self.db, "P-1", "north")


if __name__ == "__main__":
    unittest.main()
