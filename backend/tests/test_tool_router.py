import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.agent import TOOLS, _tools_for_request
from engine.graph.tools import ARGUMENT_MODELS, RiskMetricArguments, model_tool_schemas
from engine.model_provider import (
    OpenAIProvider,
    OpenRouterProvider,
    _responses_tools,
    _validate_function_tools,
)
from engine.graph.tool_router import select_tool_route
from pydantic import ValidationError


AVAILABLE = tuple(tool["function"]["name"] for tool in TOOLS)


def route(question: str, context: str = ""):
    return select_tool_route(
        question,
        context=context,
        available_tool_names=AVAILABLE,
    )


class ToolRouterTests(unittest.TestCase):
    def assertIncludes(self, result, *names):
        for name in names:
            self.assertIn(name, result.tool_names)

    def assertExcludes(self, result, *names):
        for name in names:
            self.assertNotIn(name, result.tool_names)

    def test_complete_tool_catalog_is_provider_portable(self):
        schemas = model_tool_schemas()
        canonical_names = tuple(tool["function"]["name"] for tool in schemas)

        self.assertEqual(len(canonical_names), 41)
        self.assertEqual(len(canonical_names), len(set(canonical_names)))
        self.assertEqual(set(canonical_names), set(ARGUMENT_MODELS))
        self.assertEqual(_validate_function_tools(schemas), canonical_names)

        # OpenRouter receives the canonical Chat Completions schemas. OpenAI's
        # Responses adapter flattens only the function wrapper; names and JSON
        # parameter contracts must remain byte-for-byte equivalent.
        openai_tools = _responses_tools(schemas)
        self.assertEqual(
            tuple(tool["name"] for tool in openai_tools),
            canonical_names,
        )
        for canonical, translated in zip(schemas, openai_tools):
            self.assertEqual(
                translated["parameters"],
                canonical["function"]["parameters"],
            )
            self.assertEqual(
                translated.get("description"),
                canonical["function"].get("description"),
            )

    def test_langgraph_binds_the_same_complete_catalog_to_both_providers(self):
        schemas = model_tool_schemas()
        environment = {
            "OPENAI_MODEL": "gpt-5.6-luna",
            "OPENAI_API_KEY": "test-openai-key",
            "OPENROUTER_MODEL": "test/router-model",
            "OPENROUTER_API_KEY": "test-openrouter-key",
            "DATABASE_URL": "sqlite:///:memory:",
        }
        with patch.dict(os.environ, environment, clear=True):
            openai_bound = OpenAIProvider().chat_model().bind_tools(schemas)
            openrouter_bound = OpenRouterProvider().chat_model().bind_tools(schemas)

        self.assertEqual(
            openai_bound.kwargs["tools"],
            openrouter_bound.kwargs["tools"],
        )
        self.assertEqual(len(openai_bound.kwargs["tools"]), 41)

    def test_current_project_progress_gets_focused_p6_tools(self):
        result = route(
            "What is the current progress of ASEB1PL_BAIYA_FT_600MW_PPA as of today?"
        )

        self.assertIncludes(result, "portfolio_resolve_project_id", "p6_get_project_summary")
        self.assertExcludes(
            result,
            "sap_get_po_summary",
            "tc_search_lines",
            "report_preview_project_progress",
            "get_project_kpis",
        )
        self.assertFalse(result.uses_all_tools)

    def test_monthly_block_progress_gets_block_period_tool(self):
        result = route(
            "Which block in AGE26AL_A16_FT_333MW_PPA_Commissioned — 333 MW, "
            "project ID FY25-P13 has the highest progress in the last month?"
        )

        self.assertIncludes(
            result,
            "portfolio_resolve_project_id",
            "p6_get_block_period_progress",
        )
        self.assertEqual(
            result.required_evidence_tools,
            ("p6_get_block_period_progress",),
        )

    def test_rolling_block_and_daily_trend_queries_get_event_tools(self):
        block = route(
            "Which block in AGE26AL_A16_FT_50MW_PPA_Commissioned had the highest progress in the last 30 days?"
        )
        trend = route(
            "Show daily progress trend for AGE26AL_A16_FT_50MW_PPA_Commissioned over the last 30 days"
        )

        self.assertIncludes(block, "p6_get_block_period_progress")
        self.assertIncludes(trend, "p6_get_daily_completion_trend")

    def test_transmission_readiness_and_evacuation_queries_route_to_tc(self):
        for question in (
            "What is the transmission readiness status for Project X?",
            "Is evacuation readiness aligned for Project X?",
        ):
            self.assertIncludes(route(question), "tc_get_project_lines")

    def test_project_status_with_short_alias_is_operational(self):
        result = route("what is the status of BAIYA")

        self.assertIncludes(
            result,
            "portfolio_resolve_project_id",
            "p6_get_project_summary",
        )
        self.assertEqual(result.intent, "schedule")

    def test_transmission_pronoun_follow_up_is_operational(self):
        result = route(
            "What is its transmission readiness status?",
            context="The selected project is AGE27AL_PSS09.",
        )

        self.assertIncludes(
            result,
            "portfolio_resolve_project_id",
            "tc_get_project_lines",
        )
        self.assertEqual(result.intent, "transmission")

    def test_region_transmission_query_gets_search_and_risk_tools(self):
        result = route("Which transmission lines in Rajasthan are delayed?")

        self.assertIncludes(
            result,
            "tc_search_lines",
            "tc_get_project_lines",
            "tc_get_at_risk_lines",
        )
        self.assertExcludes(result, "sap_get_po_summary", "p6_get_activities")

    def test_procurement_intents_select_relevant_sap_drilldowns(self):
        result = route("Show material delivery gaps, vendor performance and inventory for Project X")

        self.assertIncludes(
            result,
            "sap_get_po_summary",
            "sap_get_material_gaps",
            "sap_get_vendor_performance",
            "sap_get_inventory",
        )
        self.assertExcludes(result, "tc_search_lines", "p6_get_delayed_activities")

    def test_explicit_multi_domain_request_unions_domains(self):
        result = route(
            "Give the overall project progress, procurement status, and transmission exposure for Project X"
        )

        self.assertIncludes(
            result,
            "p6_get_project_summary",
            "sap_get_po_summary",
            "tc_get_project_lines",
        )
        self.assertExcludes(result, "get_project_kpis")

    def test_forward_looking_question_includes_forecast(self):
        result = route("When will Project X finish, and is it on track for commissioning?")

        self.assertIncludes(
            result,
            "portfolio_resolve_project_id",
            "p6_get_project_summary",
            "sim_forecast_completion",
        )

    def test_monthly_activity_finish_question_gets_period_forecast(self):
        result = route("How many activities are scheduled to finish this month for Project X?")

        self.assertIncludes(
            result,
            "portfolio_resolve_project_id",
            "sim_forecast_activity_finishes",
        )
        self.assertExcludes(result, "sim_forecast_completion")

    def test_yearly_activity_finish_question_gets_period_forecast(self):
        result = route("Forecast how many activities will finish in 2027 for Project X")

        self.assertIncludes(result, "sim_forecast_activity_finishes")
        self.assertExcludes(result, "sim_forecast_completion")

    def test_report_confirmation_inherits_report_context(self):
        result = route(
            "Yes, confirm and generate it.",
            context="Create a Project Progress Report for Project X in PDF and DOCX.",
        )

        self.assertIncludes(
            result,
            "report_generate_project_progress",
        )
        self.assertExcludes(result, "report_preview_project_progress")

        comparison = route(
            "Yes, generate the PDF and DOCX.",
            context="Project Comparison Report preview for Project X versus Project Y.",
        )
        self.assertIncludes(comparison, "report_generate_project_comparison")
        self.assertExcludes(comparison, "report_generate_project_progress")

    def test_generic_follow_up_inherits_one_clear_domain(self):
        result = route(
            "What about its delays?",
            context="Show the Rajasthan transmission network status.",
        )

        self.assertIncludes(result, "tc_get_at_risk_lines", "tc_search_lines")
        self.assertExcludes(result, "p6_get_delayed_activities")

    def test_follow_up_with_mixed_context_excludes_project_health_formula(self):
        result = route(
            "What about that?",
            context="Compare the P6 schedule, SAP procurement, and transmission status.",
        )

        self.assertFalse(result.uses_all_tools)
        self.assertEqual(result.tool_names, tuple(name for name in AVAILABLE if name != "get_project_kpis"))

    def test_visual_format_does_not_create_an_unrelated_business_domain(self):
        result = route("Show procurement progress as a chart for Project X")

        self.assertIncludes(result, "sap_get_po_summary", "render_chart")
        self.assertExcludes(result, "p6_get_project_summary", "tc_get_project_lines")

    def test_cross_domain_risk_does_not_calculate_project_health(self):
        result = route("What is the overall project risk for Project X?")

        self.assertIncludes(
            result,
            "p6_get_project_summary",
            "sap_get_po_summary",
            "tc_get_project_lines",
        )
        self.assertExcludes(result, "get_project_kpis")

    def test_specific_project_health_selects_health_formula_tool(self):
        result = route("What is the health of ASEJ6PL_S07_FT_300MW_PPA?")

        self.assertIncludes(
            result,
            "portfolio_resolve_project_id",
            "get_project_kpis",
        )

    def test_portfolio_health_does_not_select_project_health_formula(self):
        result = route("Show the health of all projects in the portfolio")

        self.assertIncludes(result, "p6_list_all_projects")
        self.assertExcludes(result, "get_project_kpis")

    def test_legacy_agent_exposes_health_tool_only_for_specific_project_health(self):
        specific_names = {
            tool["function"]["name"]
            for tool in _tools_for_request("What is the health of ASEJ6PL_S07_FT_300MW_PPA?")
        }
        portfolio_names = {
            tool["function"]["name"]
            for tool in _tools_for_request("Show the health of all projects in the portfolio")
        }
        progress_names = {
            tool["function"]["name"]
            for tool in _tools_for_request("Show progress for ASEJ6PL_S07_FT_300MW_PPA")
        }

        self.assertIn("get_project_kpis", specific_names)
        self.assertNotIn("get_project_kpis", portfolio_names)
        self.assertNotIn("get_project_kpis", progress_names)

    def test_genuinely_ambiguous_operational_request_keeps_all_tools(self):
        result = route("Tell me what is happening with ASEB1PL_BAIYA_FT_600MW_PPA")

        self.assertFalse(result.uses_all_tools)
        self.assertEqual(result.tool_names, tuple(name for name in AVAILABLE if name != "get_project_kpis"))

    def test_conversation_and_short_definition_do_not_expose_tools(self):
        self.assertEqual(route("Hello").tool_names, ())
        self.assertEqual(route("What is SPI?").tool_names, ())
        self.assertEqual(route("What is transmission readiness?").tool_names, ())

    def test_project_resolution_request_uses_only_resolver(self):
        result = route("Find the project ID for BAIYA solar project")

        self.assertEqual(result.tool_names, ("portfolio_resolve_project_id",))

    def test_capacity_and_quality_queries_get_named_domain_tools(self):
        self.assertIncludes(
            route("Show the capacity milestone status for Project X"),
            "capacity_get_project_status",
        )
        quality = route("Show the portfolio quality overview")
        self.assertIncludes(quality, "quality_get_portfolio_overview")
        self.assertExcludes(quality, "p6_list_all_projects")
        self.assertIncludes(
            route("Show the contractor quality scorecard"),
            "quality_get_contractor_scorecard",
        )

    def test_reporting_section_routes_match_implemented_contracts(self):
        project_report = route(
            "Generate progress report for Project X for the current period for Management Review"
        )
        block_snapshot = route("Provide a progress snapshot of all blocks in Project X")
        portfolio_report = route("Generate a portfolio-level progress report for the current period")
        comparison_report = route("Compare Project X versus Project Y and give me a proper report")
        planned_actual_curve = route("Show planned vs actual progress chart for Project X")
        milestone_risk = route("Which projects are at risk of missing planned milestones this month?")

        self.assertIncludes(project_report, "report_generate_project_progress")
        self.assertExcludes(project_report, "report_preview_project_progress")
        self.assertIncludes(block_snapshot, "p6_get_block_period_progress", "render_chart")
        self.assertIncludes(portfolio_report, "report_generate_portfolio_progress")
        self.assertExcludes(portfolio_report, "report_preview_portfolio_progress")
        self.assertExcludes(portfolio_report, "report_preview_project_progress")
        self.assertIncludes(
            comparison_report,
            "render_chart",
            "report_generate_project_comparison",
        )
        self.assertExcludes(comparison_report, "report_preview_project_progress")
        self.assertIncludes(planned_actual_curve, "p6_get_project_summary", "render_chart")
        self.assertIncludes(milestone_risk, "p6_get_portfolio_milestone_risks")

    def test_report_preview_is_reserved_for_an_explicit_preview_request(self):
        result = route("Preview the scope of a progress report for Project X")

        self.assertIncludes(result, "report_preview_project_progress")
        self.assertExcludes(result, "report_generate_project_progress")

    def test_inherently_visual_queries_auto_route_to_chart(self):
        self.assertIncludes(
            route("Show daily progress trend for Project X over the last 30 days"),
            "p6_get_daily_completion_trend",
            "render_chart",
        )
        self.assertIncludes(
            route("Compare progress of Project X vs Project Y"),
            "render_chart",
        )

    def test_risk_queries_expose_only_the_named_risk_metric_api(self):
        result = route("Show the COD risk for Project X")

        self.assertIncludes(result, "risk_get_metric")
        self.assertExcludes(result, "risk_get_command_center", "risk_get_project360")

    def test_risk_metric_schema_is_enum_and_requires_project_when_scoped(self):
        schema = next(
            item["function"]["parameters"]
            for item in model_tool_schemas()
            if item["function"]["name"] == "risk_get_metric"
        )

        self.assertIn("project360.cod_risk", schema["properties"]["metric_id"]["enum"])
        self.assertEqual(
            RiskMetricArguments.model_validate(
                {"metric_id": "command_center.overall_risk_score"}
            ).metric_id,
            "command_center.overall_risk_score",
        )
        with self.assertRaises(ValidationError):
            RiskMetricArguments.model_validate({"metric_id": "project360.cod_risk"})
        with self.assertRaises(ValidationError):
            RiskMetricArguments.model_validate({"metric_id": "unsupported.composite"})


if __name__ == "__main__":
    unittest.main()
