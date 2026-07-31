import os
import sys
from pathlib import Path
import unittest
from fastapi import HTTPException


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.tools.portfolio_tools import portfolio_resolve_project_id
from engine.graph.tools import ToolRuntimeContext, _authorize_project, _scope_project_resolution
from engine.intent import ChatIntent
from engine.orchestrator import ChatOrchestrator
import models
from services.project_catalog_service import AmbiguousProjectError, ProjectCatalogService
from routers import projects
from tests.dashboard_fixtures import (
    clear_dashboard_tables,
    create_dashboard_session_factory,
    mapping,
    seed_catalog_scenario,
)


class ProjectCatalogTests(unittest.TestCase):
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

    def test_catalog_is_mapping_authoritative_and_keeps_mapping_only_projects(self):
        projects = ProjectCatalogService.list_projects(self.db)

        self.assertEqual([project.mapping_id for project in projects], [1, 2])
        self.assertEqual({project.project_id for project in projects}, {"SOLAR-A", "WIND-B"})
        self.assertNotIn("ORPHAN-P6", {project.project_id for project in projects})

    def test_catalog_counts_duplicate_and_null_id_mapping_records(self):
        self.db.add_all([
            mapping(
                mapping_id=5,
                project_id="SOLAR-A",
                name="Alpha Solar duplicate mapping",
                cluster="North Solar",
                category="Solar",
            ),
            mapping(
                mapping_id=6,
                project_id=None,
                name="Catalog project without canonical ID",
                cluster="Other",
                category="Other",
            ),
        ])
        self.db.commit()

        projects = ProjectCatalogService.list_projects(self.db)

        self.assertEqual(len(projects), 4)
        self.assertEqual(sum(project.project_id == "SOLAR-A" for project in projects), 2)
        self.assertEqual(sum(project.project_id is None for project in projects), 1)

    def test_demo_filter_uses_mapping_preferred_name(self):
        self.db.add_all([
            mapping(
                mapping_id=5,
                project_id="VISIBLE",
                name="Demo in fallback name",
                p6_name="Approved Production Name",
                cluster="Other",
                category="Other",
            ),
            mapping(
                mapping_id=6,
                project_id="HIDDEN",
                name="Ordinary fallback",
                p6_name="Digital DEMO Project",
                cluster="Other",
                category="Other",
            ),
        ])
        self.db.commit()

        ids = {project.project_id for project in ProjectCatalogService.list_projects(self.db)}

        self.assertIn("VISIBLE", ids)
        self.assertNotIn("HIDDEN", ids)

    def test_portfolio_filter_matches_tokens_across_dashboard_fields(self):
        self.db.add(mapping(
            mapping_id=5,
            project_id="MIXED",
            name="Khavda Delivery Project",
            cluster="Solar Region",
            category="Execution",
        ))
        self.db.commit()

        spaced = ProjectCatalogService.list_projects(self.db, "solar khavda")
        plus = ProjectCatalogService.list_projects(self.db, "solar+khavda")

        self.assertEqual([project.project_id for project in spaced], ["MIXED"])
        self.assertEqual([project.project_id for project in plus], ["MIXED"])

    def test_resolution_is_case_and_whitespace_normalized(self):
        resolution = ProjectCatalogService.resolve(self.db, "  alpha   SOLAR 100mw ")

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.project.project_id, "SOLAR-A")

    def test_resolution_supports_actual_p6_name(self):
        project = self.db.query(models.P6Project).filter_by(project_id="SOLAR-A").one()
        project.name = "P6 Native Alpha Name"
        self.db.commit()

        resolution = ProjectCatalogService.resolve(self.db, "P6 Native Alpha Name")

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.project.project_id, "SOLAR-A")

    def test_resolution_supports_unique_token_alias_in_project_identity(self):
        self.db.add(mapping(
            mapping_id=5,
            project_id="FY25-BAIYA_600MW",
            name="NHPC BOO",
            p6_name="ASEB1PL_BAIYA_FT_600MW_PPA",
            cluster="Solar Rajasthan",
            category="Solar",
        ))
        self.db.commit()

        resolution = ProjectCatalogService.resolve(self.db, "BAIYA")

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.match_kind, "token_alias")
        self.assertEqual(resolution.project.project_id, "FY25-BAIYA_600MW")

    def test_shared_token_alias_returns_explicit_ambiguity(self):
        self.db.add_all([
            mapping(
                mapping_id=5,
                project_id="FY25-BAIYA_600MW",
                name="NHPC BOO",
                p6_name="ASEB1PL_BAIYA_FT_600MW_PPA",
                cluster="Solar Rajasthan",
                category="Solar",
            ),
            mapping(
                mapping_id=6,
                project_id="FY26-BAIYA_300MW",
                name="BAIYA Expansion",
                p6_name="ASEB2PL_BAIYA_FT_300MW_PPA",
                cluster="Solar Rajasthan",
                category="Solar",
            ),
        ])
        self.db.commit()

        resolution = ProjectCatalogService.resolve(self.db, "BAIYA")

        self.assertEqual(resolution.status, "ambiguous")
        self.assertEqual(resolution.match_kind, "token_alias")
        self.assertEqual(
            {candidate.project_id for candidate in resolution.candidates},
            {"FY25-BAIYA_600MW", "FY26-BAIYA_300MW"},
        )

    def test_location_cluster_alias_returns_all_project_candidates(self):
        self.db.add_all([
            mapping(
                mapping_id=5,
                project_id="KHAVDA-1",
                name="Alpha Plot",
                p6_name="ALPHA_A01_100MW",
                cluster="Solar Khavda",
                category="Solar",
            ),
            mapping(
                mapping_id=6,
                project_id="KHAVDA-2",
                name="Beta Plot",
                p6_name="BETA_A02_200MW",
                cluster="Solar Khavda",
                category="Solar",
            ),
        ])
        self.db.commit()

        resolution = ProjectCatalogService.resolve(self.db, "Khavda")
        tool_result = portfolio_resolve_project_id(self.db, "Khavda")

        self.assertEqual(resolution.status, "ambiguous")
        self.assertEqual(
            {candidate.project_id for candidate in resolution.candidates},
            {"KHAVDA-1", "KHAVDA-2"},
        )
        self.assertEqual(tool_result["status"], "ambiguous")
        self.assertTrue(all(
            candidate["cluster"] == "Solar Khavda"
            for candidate in tool_result["candidates"]
        ))

    def test_generic_words_and_capacity_are_not_project_aliases(self):
        self.assertEqual(ProjectCatalogService.resolve(self.db, "solar project").status, "not_found")
        self.assertEqual(ProjectCatalogService.resolve(self.db, "100MW").status, "not_found")

    def test_shared_spv_returns_explicit_ambiguity(self):
        self.db.add_all([
            mapping(
                mapping_id=5,
                project_id="SHARED-1",
                name="Shared One",
                cluster="Other",
                category="Other",
                spv_name="Shared SPV",
            ),
            mapping(
                mapping_id=6,
                project_id="SHARED-2",
                name="Shared Two",
                cluster="Other",
                category="Other",
                spv_name="Shared SPV",
            ),
        ])
        self.db.commit()

        result = portfolio_resolve_project_id(self.db, "Shared SPV")

        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual({candidate["project_id"] for candidate in result["candidates"]}, {"SHARED-1", "SHARED-2"})

    def test_duplicate_mappings_for_one_id_resolve_to_one_identity(self):
        self.db.add(mapping(
            mapping_id=5,
            project_id="SOLAR-A",
            name="Alpha Solar 100MW",
            cluster="North Solar",
            category="Solar",
        ))
        self.db.commit()

        resolution = ProjectCatalogService.resolve(self.db, "SOLAR-A")

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.project.mapping_id, 1)

    def test_resolution_respects_portfolio_scope(self):
        resolution = ProjectCatalogService.resolve(self.db, "Beta Wind 50MW", portfolio="North Solar")

        self.assertEqual(resolution.status, "not_found")

    def test_scoped_mappings_apply_portfolio_and_project_resolution(self):
        mappings = ProjectCatalogService.list_scoped_mappings(
            self.db,
            portfolio="North Solar",
            project_name="alpha solar 100mw",
        )

        self.assertEqual([mapping.project_id for mapping in mappings], ["SOLAR-A"])

    def test_scoped_mappings_reject_ambiguous_project_name(self):
        self.db.add_all([
            mapping(
                mapping_id=5,
                project_id="SHARED-1",
                name="Shared One",
                cluster="Other",
                category="Other",
                spv_name="Shared SPV",
            ),
            mapping(
                mapping_id=6,
                project_id="SHARED-2",
                name="Shared Two",
                cluster="Other",
                category="Other",
                spv_name="Shared SPV",
            ),
        ])
        self.db.commit()

        with self.assertRaises(AmbiguousProjectError):
            ProjectCatalogService.list_scoped_mappings(
                self.db,
                project_name="Shared SPV",
            )
        with self.assertRaises(HTTPException) as raised:
            projects.get_project_summary(project_name="Shared SPV", nocache=True, db=self.db)
        self.assertEqual(raised.exception.status_code, 409)

    def test_existence_validation_can_preserve_unmapped_p6_compatibility(self):
        self.assertFalse(ProjectCatalogService.is_known_project_id(self.db, "ORPHAN-P6"))
        self.assertTrue(ProjectCatalogService.is_known_project_id(
            self.db,
            "ORPHAN-P6",
            include_unmapped_p6=True,
        ))

    def test_graph_authorization_preserves_mapping_and_p6_only_ids(self):
        runtime = ToolRuntimeContext(
            user_id="user",
            tenant_id="tenant",
            role="executive",
            session_id="session",
            run_id="run",
            request_id="request",
        )

        _authorize_project(self.db, "WIND-B", runtime)
        _authorize_project(self.db, "ORPHAN-P6", runtime)
        with self.assertRaisesRegex(ValueError, "Unknown project"):
            _authorize_project(self.db, "UNKNOWN", runtime)

    def test_graph_authorization_keeps_exact_selected_scope(self):
        runtime = ToolRuntimeContext(
            user_id="user",
            tenant_id="tenant",
            role="executive",
            session_id="session",
            run_id="run",
            request_id="request",
            active_project_ids=("SOLAR-A",),
        )

        _authorize_project(self.db, "SOLAR-A", runtime)
        with self.assertRaisesRegex(PermissionError, "outside the selected"):
            _authorize_project(self.db, "WIND-B", runtime)

    def test_ambiguous_resolution_is_filtered_to_selected_scope(self):
        self.db.add_all([
            mapping(
                mapping_id=5,
                project_id="SHARED-1",
                name="Shared One",
                cluster="Other",
                category="Other",
                spv_name="Shared SPV",
            ),
            mapping(
                mapping_id=6,
                project_id="SHARED-2",
                name="Shared Two",
                cluster="Other",
                category="Other",
                spv_name="Shared SPV",
            ),
        ])
        self.db.commit()
        data = portfolio_resolve_project_id(self.db, "Shared SPV")
        runtime = ToolRuntimeContext(
            user_id="user",
            tenant_id="tenant",
            role="executive",
            session_id="session",
            run_id="run",
            request_id="request",
            active_project_ids=("SHARED-1",),
        )

        scoped = _scope_project_resolution(self.db, data, runtime)

        self.assertEqual(scoped["project_id"], "SHARED-1")
        self.assertNotIn("candidates", scoped)

    def test_legacy_orchestrator_keeps_ambiguity_as_clarification_context(self):
        self.db.add_all([
            mapping(
                mapping_id=5,
                project_id="SHARED-1",
                name="Shared One",
                cluster="Other",
                category="Other",
                spv_name="Shared SPV",
            ),
            mapping(
                mapping_id=6,
                project_id="SHARED-2",
                name="Shared Two",
                cluster="Other",
                category="Other",
                spv_name="Shared SPV",
            ),
        ])
        self.db.commit()
        intent = ChatIntent(projects=["Shared SPV"], intent_type="factual", domains=["p6"])

        context, _, _ = ChatOrchestrator()._gather_context(self.db, intent)

        self.assertEqual(context["project_resolution"]["status"], "ambiguous")
        self.assertNotIn("portfolio_facts", context)


if __name__ == "__main__":
    unittest.main()
