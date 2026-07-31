import os
import sys
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import models
from engine.tools.quality_tools import (
    quality_get_contractor_scorecard,
    quality_get_portfolio_overview,
    quality_get_project_status,
    quality_list_ncs,
)
from services.quality_analytics_service import QualityAnalyticsService


TABLES = (
    models.ProjectMapping.__table__,
    models.P6Project.__table__,
    models.PulseNC.__table__,
    models.PulseRFI.__table__,
)
NOW = datetime(2026, 7, 31, 12)


def mapping(mapping_id, project_id, name, *, p6_name=None, spv=None, cluster="Solar North"):
    return models.ProjectMapping(
        id=mapping_id,
        project_id=project_id,
        project=name,
        project_name_from_p6=p6_name or name,
        spv_name=spv or f"SPV-{mapping_id}",
        cluster=cluster,
        category="Solar",
    )


def nc(pulse_id, **overrides):
    values = {
        "pulse_id": pulse_id,
        "nc_label": pulse_id,
        "status": "raised",
        "category": "Non Critical",
        "project_name": "Alpha Site",
        "spv_name": "ALPHA-SPV",
        "vendor_name": "BuildCo",
        "vendor_code": "BC",
        "current_handler": "Contractor",
        "created_at": datetime(2026, 7, 30, 12),
        "last_synced_at": datetime(2026, 7, 31, 8),
    }
    values.update(overrides)
    return models.PulseNC(**values)


def rfi(pulse_id, **overrides):
    values = {
        "pulse_id": pulse_id,
        "status": "raised",
        "project_name": "Alpha Site",
        "spv_name": "ALPHA-SPV",
        "created_at": datetime(2026, 7, 30, 12),
        "last_synced_at": datetime(2026, 7, 31, 9),
    }
    values.update(overrides)
    return models.PulseRFI(**values)


class QualityAnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine, tables=TABLES)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        self.db.add_all([
            mapping(1, "P-ALPHA", "Alpha Site", p6_name="P6 Alpha", spv="ALPHA-SPV"),
            mapping(2, "P-BETA", "Beta Site", p6_name="P6 Beta", spv="BETA-SPV", cluster="Wind South"),
            models.P6Project(p6_object_id=1, project_id="P-ALPHA", name="Native Alpha Schedule"),
            models.P6Project(p6_object_id=2, project_id="P-BETA", name="Native Beta Schedule"),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def seed_formula_rows(self):
        self.db.add_all([
            nc(
                "NC-COMPLETE",
                status=" Completed ",
                category="critical",
                created_at=datetime(2026, 7, 1),
                approved_at=datetime(2026, 7, 11),
                debit=50,
                defect_type="Crack",
                vendor_name="BUILDCO",
            ),
            nc(
                "NC-CRITICAL",
                status="RAISED",
                category=" CRITICAL ",
                created_at=datetime(2026, 7, 26),
                workarea_name="Block A",
                defect_type="Crack",
            ),
            nc(
                "NC-REJECTED",
                status="Rejected",
                category="non-critical",
                created_at=datetime(2026, 6, 1),
                workarea_name="Block A",
            ),
            rfi("RFI-DONE", status="COMPLETED"),
            rfi("RFI-OPEN", status="Submitted"),
        ])
        self.db.commit()

    def test_overview_preserves_formulas_and_normalizes_case(self):
        self.seed_formula_rows()

        result = QualityAnalyticsService.portfolio_overview(self.db, now=NOW)
        data = result.to_dict()

        self.assertTrue(result.available)
        self.assertEqual((result.total_ncs, result.open_ncs, result.completed_ncs), (3, 2, 1))
        self.assertEqual(result.critical_open, 1)
        self.assertEqual(result.closure_rate, 33.3)
        self.assertEqual(result.avg_resolution_days, 10.0)
        self.assertEqual((result.total_debit, result.debit_count), (50.0, 1))
        self.assertEqual((result.total_rfis, result.open_rfis, result.rfis_completed), (2, 1, 1))
        self.assertEqual(data["by_status"], {"completed": 1, "raised": 1, "rejected": 1})
        self.assertEqual(data["by_category"], {"Critical": 2, "Non Critical": 1})
        self.assertEqual(data["aging"], {"0-3": 0, "3-7": 1, "7-14": 0, "14-30": 0, "30+": 1})
        self.assertEqual(data["top_defects"][0], {"type": "Crack", "count": 2})
        self.assertEqual(data["trends"], [
            {"month": "2026-06", "created": 1, "closed": 0},
            {"month": "2026-07", "created": 2, "closed": 1},
        ])
        self.assertEqual(data["availability"], {"quality": True, "ncs": True, "rfis": True})
        self.assertEqual(data["provenance"]["data_as_of"], "2026-07-31T08:00:00")
        self.assertEqual(data["provenance"]["formula_versions"]["overview"], "dashboard-quality-overview-v1")

    def test_project_score_rfi_totals_and_p6_name_resolution(self):
        self.seed_formula_rows()

        result = QualityAnalyticsService.project_status(self.db, "native alpha schedule", now=NOW)
        data = result.to_dict()

        self.assertEqual(result.resolution_status, "resolved")
        self.assertEqual(result.project_id, "P-ALPHA")
        self.assertEqual(result.match_kind, "p6_name")
        self.assertEqual(result.quality_score, 67)
        self.assertEqual(result.closure_rate, 33.3)
        self.assertEqual((result.total_rfis, result.open_rfis, result.rfis_completed), (2, 1, 1))
        self.assertEqual(data["blocks"], [
            {"name": "Unknown", "total": 1, "critical_open": 0, "open": 0},
            {"name": "Block A", "total": 2, "critical_open": 1, "open": 2},
        ])
        self.assertEqual(data["ncs"][0]["status"], "raised")
        self.assertEqual(data["ncs"][0]["category"], "Critical")

    def test_contractor_score_formula_and_case_insensitive_grouping(self):
        self.seed_formula_rows()

        scorecard = QualityAnalyticsService.contractor_scorecard(self.db)

        self.assertEqual(len(scorecard.contractors), 1)
        score = scorecard.contractors[0]
        self.assertEqual(score.total_ncs, 3)
        self.assertEqual(score.avg_resolution_days, 10.0)
        self.assertEqual(score.quality_score, 51)
        self.assertEqual(score.closure_rate, 33.3)

    def test_empty_states_are_explicit_and_dto_is_frozen(self):
        overview = QualityAnalyticsService.portfolio_overview(self.db, now=NOW)
        project = QualityAnalyticsService.project_status(self.db, "P-BETA", now=NOW)

        self.assertFalse(overview.available)
        self.assertEqual(overview.to_dict()["availability"], {
            "quality": False, "ncs": False, "rfis": False,
        })
        self.assertFalse(project.available)
        self.assertEqual((project.closure_rate, project.quality_score), (100, 100))
        with self.assertRaises(FrozenInstanceError):
            overview.total_ncs = 2

    def test_ambiguous_partial_and_shared_spv_are_not_arbitrarily_selected(self):
        self.db.add_all([
            mapping(3, "P-ALPHA-2", "Alpha Extension", spv="SHARED-SPV"),
            mapping(4, "P-GAMMA", "Gamma Site", spv="SHARED-SPV"),
        ])
        self.db.commit()

        partial = QualityAnalyticsService.project_status(self.db, "Alpha")
        shared = QualityAnalyticsService.project_status(self.db, "shared-spv")

        self.assertEqual(partial.resolution_status, "ambiguous")
        self.assertEqual({item[0] for item in partial.candidates}, {"P-ALPHA", "P-ALPHA-2"})
        self.assertEqual(shared.resolution_status, "ambiguous")
        self.assertEqual({item[0] for item in shared.candidates}, {"P-ALPHA-2", "P-GAMMA"})
        self.assertEqual(shared.warnings[0].reason, "ambiguous_project")

    def test_unmatched_and_colliding_source_rows_emit_warnings(self):
        self.db.add_all([
            mapping(3, "P-GAMMA", "Gamma Site", spv="ALPHA-SPV"),
            nc("NC-AMBIG", project_name=None, project_id=None, spv_name="ALPHA-SPV"),
            nc("NC-MISSING", project_name="No Catalog Project", project_id=None, spv_name=None),
        ])
        self.db.commit()

        snapshots = QualityAnalyticsService.project_snapshots(self.db, now=NOW)
        warnings = snapshots[0].warnings

        self.assertEqual({warning.reason for warning in warnings}, {"ambiguous_project", "unmatched_project"})
        self.assertTrue(all(snapshot.total_ncs == 0 for snapshot in snapshots))

    def test_portfolio_scope_excludes_other_projects_and_unmatched_rows(self):
        self.db.add_all([
            nc("NC-ALPHA"),
            nc("NC-BETA", project_name="Beta Site", spv_name="BETA-SPV"),
            nc("NC-UNKNOWN", project_name="Unknown Site", spv_name=None),
        ])
        self.db.commit()

        result = QualityAnalyticsService.portfolio_overview(self.db, "Solar North", now=NOW)

        self.assertEqual(result.total_ncs, 1)
        self.assertEqual(result.provenance.nc_source_ids, ("NC-ALPHA",))
        self.assertEqual(len(result.warnings), 2)

    def test_bulk_project_snapshots_have_bounded_query_count(self):
        self.db.add_all([nc("NC-ALPHA"), nc("NC-BETA", project_name="Beta Site", spv_name="BETA-SPV")])
        self.db.commit()
        statements = []

        def count_queries(*args):
            statements.append(args[2])

        event.listen(self.engine, "before_cursor_execute", count_queries)
        try:
            snapshots = QualityAnalyticsService.project_snapshots(self.db, now=NOW)
        finally:
            event.remove(self.engine, "before_cursor_execute", count_queries)

        self.assertEqual({snapshot.project_id: snapshot.total_ncs for snapshot in snapshots}, {
            "P-ALPHA": 1, "P-BETA": 1,
        })
        self.assertLessEqual(len(statements), 4)

    def test_list_filters_are_normalized_and_paginated(self):
        self.db.add_all([
            nc("NC-1", status="RAISED", category="critical"),
            nc("NC-2", status="raised", category="Critical"),
            nc("NC-3", status="completed", category="Critical"),
        ])
        self.db.commit()

        result = QualityAnalyticsService.list_ncs(
            self.db, status=" raised ", category="CRITICAL", page=2, page_size=1, now=NOW
        )

        self.assertEqual(result.total, 2)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].status, "raised")
        self.assertEqual(result.items[0].category, "Critical")

    def test_thin_tools_return_plain_compatibility_dicts(self):
        self.db.add_all([nc("NC-1"), rfi("RFI-1")])
        self.db.commit()

        overview = quality_get_portfolio_overview(self.db)
        project = quality_get_project_status(self.db, "P-ALPHA")
        contractors = quality_get_contractor_scorecard(self.db)
        listed = quality_list_ncs(self.db, project="P-ALPHA")

        self.assertIsInstance(overview, dict)
        self.assertEqual(project["project_id"], "P-ALPHA")
        self.assertEqual(contractors["contractors"][0]["name"], "BuildCo")
        self.assertEqual(listed["items"][0]["id"], "NC-1")


if __name__ == "__main__":
    unittest.main()
