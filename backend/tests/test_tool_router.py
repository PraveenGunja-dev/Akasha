import os
import sys
from pathlib import Path
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.agent import TOOLS, _tools_for_request
from engine.graph.tool_router import select_tool_route


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
            "report_preview_project_progress",
            "report_generate_project_progress",
        )

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

    def test_project_resolution_request_uses_only_resolver(self):
        result = route("Find the project ID for BAIYA solar project")

        self.assertEqual(result.tool_names, ("portfolio_resolve_project_id",))


if __name__ == "__main__":
    unittest.main()
