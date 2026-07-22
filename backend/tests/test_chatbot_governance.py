import os
import sys
import unittest
from datetime import datetime
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import models
from engine.agent import execute_tool, parse_tool_result, run_deep_analysis_agent
from engine.cache import _compare_sync_times
from engine.contracts import ChatRequestContract, ChatResponse, UserScope
from engine.intent import ChatIntent, classify_intent, normalize_intent
from engine.memory import get_relevant_feedback
from engine.orchestrator import ChatOrchestrator
from engine.project_resolver import resolve_project, resolve_projects_from_intent
from engine.tools.p6_tools import (
    p6_get_block_status,
    p6_get_pending_activities,
    p6_get_portfolio_critical_activities,
    p6_get_project_summary,
)
from engine.tools.portfolio_tools import portfolio_resolve_project_id
from engine.verifier import verify_numeric_claims
from evaluation.run_golden_eval import run_cases
from routers.ai import _suggestions_for_response


class ChatbotGovernanceTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine)

    def test_missing_sync_timestamp_is_stale(self):
        self.assertTrue(_compare_sync_times(
            {"p6_synced_at": "2026-07-18T00:00:00", "sap_synced_at": None, "tc_synced_at": None},
            {"p6_synced_at": None, "sap_synced_at": None, "tc_synced_at": None},
        ))
        self.assertTrue(_compare_sync_times(
            {"p6_synced_at": None, "sap_synced_at": None, "tc_synced_at": None},
            {"p6_synced_at": "2026-07-18T00:00:00", "sap_synced_at": None, "tc_synced_at": None},
        ))

    def test_project_resolver_clarifies_close_matches(self):
        db = self.Session()
        db.add_all([
            models.ProjectMapping(project_id="P-100", project="Khavda Solar Block 1", project_name_from_p6="Khavda Block 1"),
            models.ProjectMapping(project_id="P-101", project="Khavda Solar Block 2", project_name_from_p6="Khavda Block 2"),
        ])
        db.commit()

        result = resolve_project(db, "Khavda Solar")

        self.assertEqual(result.status, "ambiguous")
        self.assertGreaterEqual(len(result.candidates), 2)
        db.close()

    def test_project_resolver_returns_exact_project_id(self):
        db = self.Session()
        db.add(models.ProjectMapping(project_id="FY25-BAIYA", project="Baiya Solar", project_name_from_p6="Baiya Solar Project"))
        db.commit()

        result = resolve_project(db, "FY25-BAIYA")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.project_ids, ["FY25-BAIYA"])
        db.close()

    def test_project_resolver_prefers_exact_p6_id_over_shorter_mapping_prefix(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-P16",
            project="Generic 400 MW Internal",
            project_name_from_p6="Generic 400 MW Internal",
        ))
        db.add(models.P6Project(
            p6_object_id=1601,
            project_id="GEN-P16-3-2",
            name="Generic 600 MW Plant",
            status="Active",
            start_date=datetime(2026, 1, 1),
            finish_date=datetime(2026, 12, 31),
            planned_duration=2400,
            actual_duration=800,
        ))
        db.commit()

        result = resolve_project(db, "GEN-P16-3-2")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.project_ids, ["GEN-P16-3-2"])
        db.close()

    def test_project_resolver_resolves_exact_p6_name_without_mapping_row(self):
        db = self.Session()
        db.add(models.P6Project(
            p6_object_id=1602,
            project_id="GEN-P17-1-1",
            name="Generic Unmapped P6 Project",
            status="Active",
        ))
        db.commit()

        result = resolve_project(db, "Generic Unmapped P6 Project")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.project_ids, ["GEN-P17-1-1"])
        db.close()

    def test_selected_p6_project_hint_is_not_rewritten_to_mapping_prefix(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-P18",
            project="Generic Split Internal",
            project_name_from_p6="Generic Split Internal",
        ))
        db.add(models.P6Project(
            p6_object_id=1603,
            project_id="GEN-P18-9-1",
            name="Generic Selected P6 Project",
            status="Active",
            planned_duration=100,
            actual_duration=25,
        ))
        db.commit()

        resolution = resolve_projects_from_intent(
            db,
            ["GEN-P18-9-1"],
            message="actual duration? planned duration?",
            is_portfolio=False,
        )

        self.assertEqual(resolution.status, "resolved")
        self.assertEqual(resolution.project_ids, ["GEN-P18-9-1"])
        summary = p6_get_project_summary(db, resolution.project_ids[0])
        self.assertEqual(summary["planned_duration"], 100)
        self.assertEqual(summary["actual_duration"], 25)
        db.close()

    def test_project_resolver_preserves_code_words_that_are_stopwords(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-STATUS_100MW",
            project="Generic Status Project",
            project_name_from_p6="Generic Status Project P6",
        ))
        db.commit()

        result = resolve_project(
            db,
            None,
            message="Give me the current status of project GEN-STATUS",
        )

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.project_ids, ["GEN-STATUS_100MW"])
        db.close()

    def test_tc_delayed_line_count_is_portfolio_without_project_name(self):
        intent = classify_intent(
            "how many transmission delayed lines are there ?",
            use_llm=False,
        )

        self.assertEqual(intent.intent_type, "factual")
        self.assertEqual(intent.projects, [])
        self.assertTrue(intent.is_portfolio)
        self.assertIn("tc", intent.domains)

    def test_tc_delayed_line_count_normalizes_llm_non_portfolio_intent(self):
        intent = normalize_intent(
            "how many transmission delayed lines are there ?",
            ChatIntent(
                projects=[],
                intent_type="factual",
                domains=["tc"],
                is_portfolio=False,
            ),
        )

        self.assertTrue(intent.is_portfolio)
        self.assertEqual(intent.projects, [])

    def test_general_duration_driver_question_does_not_become_project_search(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-DURATION_100MW",
            project="Generic Duration Project",
            project_name_from_p6="Generic Duration Project P6",
        ))
        db.commit()

        message = "Which activity dictates the overall project duration?"
        intent = classify_intent(message, use_llm=False)
        resolution = resolve_projects_from_intent(
            db,
            intent.projects,
            message=message,
            is_portfolio=intent.is_portfolio,
        )

        self.assertTrue(intent.is_portfolio)
        self.assertEqual(resolution.status, "not_project_specific")
        db.close()

    def test_selected_project_hint_keeps_critical_path_question_project_specific(self):
        intent = classify_intent(
            "Which activities are on the critical path?",
            project_names=["FY25-BAIYA"],
            use_llm=False,
        )

        self.assertFalse(intent.is_portfolio)

    def test_placeholder_project_question_asks_clean_project_clarification(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-PROGRESS_100MW",
            project="Generic Progress Project",
            project_name_from_p6="Generic Progress Project P6",
        ))
        db.commit()

        message = "What is the current progress of X solar project at Y location for TIME_PERIOD"
        intent = classify_intent(message, use_llm=False)
        resolution = resolve_projects_from_intent(
            db,
            intent.projects,
            message=message,
            is_portfolio=intent.is_portfolio,
        )

        self.assertEqual(resolution.status, "not_found")
        self.assertEqual(resolution.question, "Which project should I use?")
        db.close()

    def test_portfolio_critical_activity_tool_returns_p6_evidence(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-CRITICAL_100MW",
            project="Generic Critical Project",
            project_name_from_p6="Generic Critical Project P6",
        ))
        db.add(models.P6Project(
            p6_object_id=2001,
            project_id="GEN-CRITICAL_100MW",
            name="Generic Critical Project P6",
            status="Active",
        ))
        db.add_all([
            models.P6Activity(
                p6_object_id=3001,
                activity_id="A-CRIT-1",
                name="Module Installation",
                status="In Progress",
                total_float=-48,
                project_object_id=2001,
            ),
            models.P6Activity(
                p6_object_id=3002,
                activity_id="A-NONCRIT-1",
                name="Internal Review",
                status="Not Started",
                total_float=96,
                project_object_id=2001,
            ),
        ])
        db.commit()

        result = p6_get_portfolio_critical_activities(db, limit=5)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Module Installation")
        self.assertEqual(result[0]["project_name"], "Generic Critical Project P6")
        self.assertEqual(result[0]["_source_table"], "p6_activity")
        db.close()

    def test_p6_pending_activities_excludes_completed_delayed_work(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-PENDING_100MW",
            project="Generic Pending Project",
            project_name_from_p6="Generic Pending Project P6",
        ))
        db.add(models.P6Project(
            p6_object_id=2101,
            project_id="GEN-PENDING_100MW",
            name="Generic Pending Project P6",
            status="Active",
        ))
        db.add_all([
            models.P6Activity(
                p6_object_id=3101,
                activity_id="PEND-1",
                name="Punch Point Closure",
                status="In Progress",
                percent_complete=0.25,
                remaining_duration=16,
                finish_date=datetime(2026, 2, 20),
                baseline_finish_date=datetime(2026, 2, 1),
                project_object_id=2101,
            ),
            models.P6Activity(
                p6_object_id=3102,
                activity_id="PEND-2",
                name="HOTO Sign Off",
                status="Not Started",
                percent_complete=0.0,
                remaining_duration=8,
                finish_date=datetime(2026, 2, 25),
                baseline_finish_date=datetime(2026, 2, 1),
                total_float=0,
                project_object_id=2101,
            ),
            models.P6Activity(
                p6_object_id=3103,
                activity_id="DONE-1",
                name="Completed But Late",
                status="Completed",
                percent_complete=1.0,
                remaining_duration=0,
                finish_date=datetime(2026, 3, 1),
                baseline_finish_date=datetime(2026, 2, 1),
                project_object_id=2101,
            ),
        ])
        db.commit()

        result = p6_get_pending_activities(db, "GEN-PENDING_100MW")

        self.assertEqual(result["total_pending"], 2)
        self.assertEqual(result["status_breakdown"], {"In Progress": 1, "Not Started": 1})
        self.assertEqual(result["delayed_pending_count"], 2)
        self.assertEqual([activity["activity_id"] for activity in result["activities"]], ["PEND-1", "PEND-2"])
        self.assertEqual(result["activities"][1]["percent_complete"], 0.0)
        db.close()

    def test_p6_block_status_reports_cod_pending_blocks(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-BLOCK_100MW",
            project="Generic Block Project",
            project_name_from_p6="Generic Block Project P6",
        ))
        db.add(models.P6Project(
            p6_object_id=2201,
            project_id="GEN-BLOCK_100MW",
            name="Generic Block Project P6",
            status="Active",
        ))
        db.add_all([
            models.P6WBSNode(
                p6_object_id=4101,
                project_object_id=2201,
                wbs_name="BLOCK-01",
            ),
            models.P6WBSNode(
                p6_object_id=4102,
                project_object_id=2201,
                wbs_name="BLOCK-02",
            ),
            models.P6Activity(
                p6_object_id=3201,
                activity_id="B1-COD",
                name="Block-01 -COD",
                status="Completed",
                percent_complete=1.0,
                actual_finish_date=datetime(2026, 1, 10),
                finish_date=datetime(2026, 1, 10),
                project_object_id=2201,
            ),
            models.P6Activity(
                p6_object_id=3202,
                activity_id="B2-TR",
                name="Block-02 -Trial Run Certificate",
                status="Completed",
                percent_complete=1.0,
                actual_finish_date=datetime(2026, 1, 12),
                finish_date=datetime(2026, 1, 12),
                project_object_id=2201,
            ),
            models.P6Activity(
                p6_object_id=3203,
                activity_id="B2-COD",
                name="Block-02 -COD",
                status="Not Started",
                percent_complete=0.0,
                project_object_id=2201,
            ),
        ])
        db.commit()

        result = p6_get_block_status(db, "GEN-BLOCK_100MW")

        self.assertEqual(result["total_blocks"], 2)
        self.assertEqual(result["cod_completed_blocks"], 1)
        self.assertEqual(result["pending_cod_blocks"], 1)
        self.assertEqual(result["trial_run_completed_cod_pending_blocks"], 1)
        self.assertEqual(result["pending_blocks"][0]["block"], "BLOCK-2")
        self.assertEqual(result["pending_blocks"][0]["overall_status"], "Trial Run Completed; COD Pending")
        db.close()

    def test_pending_activity_formatter_distinguishes_activities_from_blocks(self):
        orchestrator = ChatOrchestrator()
        content = orchestrator._format_pending_activities_answer({
            "project_name": "Generic Pending Project P6",
            "total_pending": 2,
            "status_breakdown": {"In Progress": 1, "Not Started": 1},
            "delayed_pending_count": 2,
            "critical_pending_count": 1,
            "activities": [
                {
                    "name": "Block-01 -Punch Point Rectification",
                    "status": "In Progress",
                    "drift_days": 14,
                },
                {
                    "name": "Block-02 -HOTO Sign Off",
                    "status": "Not Started",
                    "drift_days": 21,
                },
            ],
        })

        self.assertIn("pending P6 schedule activities", content)
        self.assertIn("**Summary**", content)
        self.assertIn("In Progress: **1**", content)
        self.assertIn("Not Started: **1**", content)
        self.assertIn("does not mean the COD block itself is pending", content)
        self.assertIn("**In Progress**", content)
        self.assertIn("**Not Started**", content)

    def test_deep_analysis_project_tool_resolves_generic_project_id_alias(self):
        db = self.Session()
        db.add_all([
            models.ProjectMapping(
                project_id="GEN-OTHER-001",
                project="Unrelated Project",
                project_name_from_p6="Unrelated Project P6 Name",
                spv_name="",
            ),
            models.ProjectMapping(
                project_id="GEN-ALPHA_200MW",
                project="Generic Alpha Project",
                project_name_from_p6="Generic Alpha Expansion",
                spv_name="ALPHASPV",
            ),
        ])
        db.commit()

        result = portfolio_resolve_project_id(db, "Give me the current status of project GEN-ALPHA")

        self.assertIsNotNone(result)
        self.assertEqual(result["project_id"], "GEN-ALPHA_200MW")
        db.close()

    def test_deep_analysis_project_tool_resolves_unmapped_p6_project(self):
        db = self.Session()
        db.add(models.P6Project(
            p6_object_id=1604,
            project_id="GEN-P19-7-4",
            name="Generic P6 Only Project",
            status="Active",
        ))
        db.commit()

        result = portfolio_resolve_project_id(db, "Generic P6 Only Project")

        self.assertIsNotNone(result)
        self.assertEqual(result["project_id"], "GEN-P19-7-4")
        self.assertEqual(result["project_name"], "Generic P6 Only Project")
        db.close()

    def test_p6_summary_marks_project_delayed_from_baseline_slip(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-SCHEDULE_100MW",
            project="Generic Schedule Project",
            project_name_from_p6="Generic Schedule Project P6",
        ))
        db.add(models.P6Project(
            p6_object_id=1001,
            project_id="GEN-SCHEDULE_100MW",
            name="Generic Schedule Project P6",
            status="Active",
            duration_percent_complete=0.62,
            baseline_finish_date=datetime(2026, 3, 1),
            scheduled_finish_date=datetime(2026, 5, 15),
        ))
        db.commit()

        result = p6_get_project_summary(db, "GEN-SCHEDULE_100MW")

        self.assertEqual(result["schedule_status"], "Delayed")
        self.assertEqual(result["progress_percent"], 62.0)
        self.assertEqual(result["baseline_variance_days"], 75)
        db.close()

    def test_p6_summary_includes_cost_fields_for_capex_questions(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-COST_100MW",
            project="Generic Cost Project",
            project_name_from_p6="Generic Cost Project P6",
        ))
        db.add(models.P6Project(
            p6_object_id=1701,
            project_id="GEN-COST_100MW",
            name="Generic Cost Project P6",
            status="Active",
            planned_cost=12000000,
            actual_total_cost=3000000,
            current_budget=15000000,
            baseline_total_cost=14000000,
            total_cost_variance=-1000000,
        ))
        db.commit()

        result = p6_get_project_summary(db, "GEN-COST_100MW")

        self.assertEqual(result["current_budget"], 15000000)
        self.assertEqual(result["planned_cost"], 12000000)
        self.assertEqual(result["actual_total_cost"], 3000000)
        self.assertEqual(result["baseline_total_cost"], 14000000)
        self.assertEqual(result["total_cost_variance"], -1000000)
        db.close()

    def test_deterministic_metric_answers_cover_dates_durations_and_cost(self):
        orchestrator = ChatOrchestrator()
        intent = ChatIntent(projects=["GEN-METRIC_100MW"], intent_type="factual", domains=["p6"])
        context = {
            "GEN-METRIC_100MW": {
                "p6_summary": {
                    "project_name": "Generic Metric Project P6",
                    "start_date": "2026-01-01T08:00:00",
                    "finish_date": "2026-12-31T16:00:00",
                    "planned_start": "2026-01-01T00:00:00",
                    "scheduled_finish": "2027-01-15T16:00:00",
                    "projected_finish": "2027-01-15T16:00:00",
                    "baseline_start": "2026-01-01T08:00:00",
                    "baseline_finish": "2026-12-15T16:00:00",
                    "planned_duration": 2400,
                    "actual_duration": 1200,
                    "remaining_duration": 600,
                    "baseline_duration": 2200,
                    "current_budget": 15000000,
                    "planned_cost": 12000000,
                    "actual_total_cost": 3000000,
                    "baseline_total_cost": 14000000,
                    "total_cost_variance": -1000000,
                },
                "sap_po_summary": {
                    "has_data": True,
                    "summary": {"total_value_inr": 12500000},
                },
            }
        }

        dates = orchestrator._try_deterministic_answer("what are the start date and end dates?", context, intent)
        durations = orchestrator._try_deterministic_answer("actual duration? planned duration?", context, intent)
        capex = orchestrator._try_deterministic_answer("what is the capex of the project?", context, intent)

        self.assertIn("Start date", dates)
        self.assertIn("2026-01-01", dates)
        self.assertIn("Planned duration", durations)
        self.assertIn("2400 hours", durations)
        self.assertIn("Current budget", capex)
        self.assertIn("INR 1.50 Cr", capex)

    def test_deep_analysis_current_status_uses_deterministic_project_summary(self):
        db = self.Session()
        db.add(models.ProjectMapping(
            project_id="GEN-STATUS_100MW",
            project="Generic Status Project",
            project_name_from_p6="Generic Status Project P6",
        ))
        db.add(models.P6Project(
            p6_object_id=1002,
            project_id="GEN-STATUS_100MW",
            name="Generic Status Project P6",
            status="Active",
            duration_percent_complete=0.5,
            baseline_finish_date=datetime(2026, 1, 1),
            scheduled_finish_date=datetime(2026, 2, 1),
        ))
        db.commit()
        scope = UserScope(
            role="admin",
            project_ids=["*"],
            domains=["*"],
            can_access_portfolio=True,
            is_authenticated=True,
        )

        content, tools_used, tool_results = run_deep_analysis_agent(
            db,
            "Give me the current status of project GEN-STATUS",
            history=[],
            user_scope=scope,
        )

        self.assertIn("is Delayed", content)
        self.assertIn("Management Review", content)
        self.assertNotIn("GEN-STATUS_100MW", content)
        self.assertIn("p6_get_project_summary", tools_used)
        self.assertTrue(tool_results)
        db.close()

    def test_no_followup_suggestions_for_project_resolution_failure(self):
        response = ChatResponse(
            content="I could not match that project.",
            intent_type="analytical",
            project_ids=[],
            domains=["p6"],
            warnings=["project_resolution_required"],
            latency_ms=0,
            status="clarification",
        )

        self.assertEqual(_suggestions_for_response(response), [])

    def test_followup_suggestions_are_based_on_successful_sources(self):
        response = ChatResponse(
            content="Project is delayed.",
            intent_type="deep_analysis",
            project_ids=["GEN-STATUS_100MW"],
            domains=["p6", "sap"],
            sources_used=["p6_project", "mt_poamount"],
            latency_ms=0,
            status="success",
        )

        suggestions = _suggestions_for_response(response)

        self.assertIn("List the evidence used", suggestions)
        self.assertIn("Summarize schedule risks", suggestions)
        self.assertIn("Summarize procurement gaps", suggestions)

    def test_only_reviewed_approved_feedback_is_injected(self):
        db = self.Session()
        db.add_all([
            models.ChatFeedback(
                message_id=1,
                feedback_type="correction",
                correction_text="Unreviewed correction",
                question_pattern="what is spi",
                is_reviewed=False,
                trust_level="unreviewed",
                created_at=datetime.utcnow(),
            ),
            models.ChatFeedback(
                message_id=2,
                feedback_type="correction",
                correction_text="Approved correction",
                question_pattern="what is spi",
                is_reviewed=True,
                trust_level="approved",
                created_at=datetime.utcnow(),
            ),
        ])
        db.commit()

        feedback = get_relevant_feedback(db, question="what is spi")

        self.assertEqual([item["correction"] for item in feedback], ["Approved correction"])
        db.close()

    def test_invalid_tool_result_is_normalized_to_error_envelope(self):
        envelope = parse_tool_result("not-json")

        self.assertEqual(envelope["status"], "error")
        self.assertEqual(envelope["evidence"], [])
        self.assertIn("invalid result envelope", envelope["error"])

    def test_deep_analysis_tool_metadata_becomes_response_metadata(self):
        orchestrator = ChatOrchestrator()
        tool_results = [{
            "tool_name": "p6_get_project_summary",
            "status": "success",
            "data": {},
            "evidence": [{
                "source_system": "P6",
                "source_type": "p6_project",
                "record_ids": ["FY25-BAIYA"],
                "project_id": "FY25-BAIYA",
                "as_of": "2026-07-20T00:00:00",
                "retrieved_at": "2026-07-20T00:01:00",
                "calculation": None,
                "calculation_version": None,
            }],
            "warnings": ["source partially stale"],
            "error": None,
        }]

        freshness, sources, evidence, warnings, domains, project_ids = orchestrator._metadata_from_tool_results(tool_results)

        self.assertEqual(sources, ["p6_project"])
        self.assertEqual(domains, ["p6"])
        self.assertEqual(project_ids, ["FY25-BAIYA"])
        self.assertEqual(freshness["p6"].status, "fresh")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(warnings, ["source partially stale"])

    def test_fast_path_blocks_out_of_scope_project_before_context_gathering(self):
        intent = ChatIntent(
            projects=["FY25-BAIYA"],
            intent_type="factual",
            domains=["p6"],
        )
        scope = UserScope(
            role="projects",
            project_ids=["FY25-OTHER"],
            domains=["p6"],
            is_authenticated=True,
        )

        response = ChatOrchestrator()._authorization_failure(intent, scope, latency_ms=0)

        self.assertIsNotNone(response)
        self.assertEqual(response.status, "error")
        self.assertEqual(response.project_ids, [])
        self.assertIn("unauthorized_project_access", response.warnings)

    def test_fast_path_blocks_out_of_scope_domain_before_context_gathering(self):
        intent = ChatIntent(
            projects=["FY25-BAIYA"],
            intent_type="factual",
            domains=["tc"],
        )
        scope = UserScope(
            role="projects",
            project_ids=["FY25-BAIYA"],
            domains=["p6"],
            is_authenticated=True,
        )

        response = ChatOrchestrator()._authorization_failure(intent, scope, latency_ms=0)

        self.assertIsNotNone(response)
        self.assertEqual(response.status, "error")
        self.assertEqual(response.project_ids, ["FY25-BAIYA"])
        self.assertEqual(response.domains, [])
        self.assertIn("unauthorized_domain_access", response.warnings)

    def test_deep_analysis_tool_call_returns_unauthorized_envelope_for_out_of_scope_project(self):
        db = self.Session()
        scope = UserScope(
            role="projects",
            project_ids=["FY25-OTHER"],
            domains=["p6"],
            is_authenticated=True,
        )

        envelope = parse_tool_result(execute_tool(
            db,
            "p6_get_project_summary",
            {"project_id": "FY25-BAIYA"},
            user_scope=scope,
        ))

        self.assertEqual(envelope["status"], "unauthorized")
        self.assertIsNone(envelope["data"])
        self.assertEqual(envelope["evidence"], [])
        self.assertIn("outside the user's project scope", envelope["warnings"][0])
        db.close()

    def test_deep_analysis_tool_call_blocks_portfolio_tools_for_restricted_role(self):
        db = self.Session()
        scope = UserScope(
            role="projects",
            project_ids=["FY25-BAIYA"],
            domains=["p6"],
            can_access_portfolio=False,
            is_authenticated=True,
        )

        envelope = parse_tool_result(execute_tool(
            db,
            "p6_list_all_projects",
            {},
            user_scope=scope,
        ))

        self.assertEqual(envelope["status"], "unauthorized")
        self.assertIsNone(envelope["data"])
        self.assertEqual(envelope["evidence"], [])
        self.assertIn("Portfolio-wide tool access", envelope["warnings"][0])
        db.close()

    def test_deep_analysis_tool_call_validates_required_arguments(self):
        db = self.Session()
        scope = UserScope(
            role="admin",
            project_ids=["*"],
            domains=["*"],
            can_access_portfolio=True,
            is_authenticated=True,
        )

        envelope = parse_tool_result(execute_tool(
            db,
            "p6_get_project_summary",
            {},
            user_scope=scope,
        ))

        self.assertEqual(envelope["status"], "error")
        self.assertIsNone(envelope["data"])
        self.assertEqual(envelope["evidence"], [])
        self.assertIn("Invalid tool arguments", envelope["error"])
        self.assertIn("project_id", envelope["warnings"][0])
        db.close()

    def test_deep_analysis_tool_call_rejects_unknown_tool_before_authorization(self):
        db = self.Session()
        scope = UserScope(
            role="projects",
            project_ids=["FY25-BAIYA"],
            domains=["p6"],
            can_access_portfolio=False,
            is_authenticated=True,
        )

        envelope = parse_tool_result(execute_tool(
            db,
            "nonexistent_write_tool",
            {"project_id": "FY25-BAIYA"},
            user_scope=scope,
        ))

        self.assertEqual(envelope["status"], "error")
        self.assertEqual(envelope["error"], "Unknown tool: nonexistent_write_tool")
        self.assertIsNone(envelope["data"])
        db.close()

    def test_chat_request_contract_accepts_frontend_aliases(self):
        request = ChatRequestContract(
            message="Why is project FY25-BAIYA at risk?",
            projectId="FY25-BAIYA",
            sessionId="thread-1",
            isDeepAnalysis=True,
            imageData=None,
            mode="analysis",
        )

        self.assertEqual(request.contract_version, "chat.request.v1")
        self.assertEqual(request.project_id, "FY25-BAIYA")
        self.assertEqual(request.session_id, "thread-1")
        self.assertTrue(request.is_deep_analysis)

    def test_chat_request_contract_rejects_blank_message(self):
        with self.assertRaises(Exception):
            ChatRequestContract(message="   ")

    def test_deterministic_golden_dataset_passes(self):
        report = run_cases()

        self.assertEqual(report["failed"], 0, report)
        self.assertGreaterEqual(report["total"], 15)

    def test_numeric_verifier_accepts_numbers_present_in_context(self):
        warnings = verify_numeric_claims(
            "SPI is 0.82 and pending quantity is 125 units.",
            {"p6": {"spi": 0.82}, "sap": {"pending": 125}},
        )

        self.assertEqual(warnings, [])

    def test_numeric_verifier_warns_on_material_number_absent_from_context(self):
        warnings = verify_numeric_claims(
            "SPI is 0.82 and recovery will save 45 days.",
            {"p6": {"spi": 0.82}},
        )

        self.assertEqual(warnings, ["unverified_numeric_claims: 45"])


if __name__ == "__main__":
    unittest.main()
