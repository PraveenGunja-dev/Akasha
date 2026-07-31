import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from typing import ClassVar


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from engine.graph.builder import InvalidModelResponse, SYSTEM_PROMPT, build_chat_graph
from engine.graph.service import ChatGraphService
from engine.graph.tools import ToolExecution, parse_raw_tool_call


class ToolCapableFakeModel(GenericFakeChatModel):
    def bind_tools(self, _tools, **_kwargs):
        return self


class ToolBindingCaptureFakeModel(ToolCapableFakeModel):
    bound_tool_sets: ClassVar[list[tuple[str, ...]]] = []

    def bind_tools(self, tools, **_kwargs):
        self.bound_tool_sets.append(tuple(
            tool["function"]["name"] for tool in tools
        ))
        return self


def conversational_answer(text: str) -> str:
    return text


def graph_input(user_id: str, user_message_id: int, assistant_message_id: int, text: str):
    return {
        "messages": [HumanMessage(content=text, id=f"chat-message:{user_message_id}")],
        "user_id": user_id,
        "tenant_id": "tenant",
        "session_id": "thread",
        "user_role": "executive",
        "request_id": f"request-{user_message_id}",
        "current_user_message_id": user_message_id,
        "current_assistant_message_id": assistant_message_id,
        "active_project_ids": [],
        "tool_names": [],
        "visualizations": [],
    }


class GraphStructureTests(unittest.TestCase):
    def test_system_prompt_defaults_to_adaptive_executive_answers(self):
        self.assertIn("answer the exact question in the first sentence", SYSTEM_PROMPT)
        self.assertIn("roughly 80-180 words", SYSTEM_PROMPT)
        self.assertIn("Expand when the user asks", SYSTEM_PROMPT)
        self.assertIn("Never discuss tools", SYSTEM_PROMPT)
        self.assertIn("Do not append unsolicited recommendations", SYSTEM_PROMPT)
        self.assertIn("forecast_vs_reference_days", SYSTEM_PROMPT)
        self.assertIn("Never call `actual_duration` earned hours", SYSTEM_PROMPT)
        self.assertIn("When project resolution is ambiguous", SYSTEM_PROMPT)

    def test_tool_loop_forces_final_answer_at_configured_model_call_limit(self):
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content="", tool_calls=[{
                "name": "tc_get_network_summary",
                "args": {},
                "id": "call-1",
            }]),
            AIMessage(content=conversational_answer("bounded final answer")),
        ]))
        state = graph_input("user-a", 1, 2, "broad request")
        state["run_id"] = "a" * 32
        with patch.dict(os.environ, {"AKASHA_GRAPH_MAX_MODEL_CALLS": "2"}), patch(
            "engine.graph.builder._ensure_run_active", return_value=None
        ), patch(
            "engine.graph.builder.execute_authenticated_tool",
            return_value=ToolExecution('{"status":"ok","data":{}}', "ok"),
        ):
            graph = build_chat_graph(model, context_window=32_768)
            result = graph.invoke(state)
        self.assertEqual(result["agent_iterations"], 2)
        self.assertEqual(result["tool_names"], ["tc_get_network_summary"])
        self.assertEqual(result["messages"][-1].content, "bounded final answer")

    def test_graph_binds_only_routed_tools_for_clear_progress_question(self):
        ToolBindingCaptureFakeModel.bound_tool_sets = []
        model = ToolBindingCaptureFakeModel(messages=iter([
            AIMessage(content="", tool_calls=[{
                "name": "portfolio_resolve_project_id",
                "args": {"name": "BAIYA solar project"},
                "id": "call-1",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "p6_get_project_summary",
                "args": {"project_id": "FY25-BAIYA_600MW"},
                "id": "call-2",
            }]),
            AIMessage(content="The project is 61.2% complete as of 11 July 2026."),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        state = graph_input(
            "user-a",
            1,
            2,
            "What is the current progress of the BAIYA solar project?",
        )
        state["run_id"] = "a" * 32

        with patch("engine.graph.builder._ensure_run_active", return_value=None), patch(
            "engine.graph.builder.execute_authenticated_tool",
            side_effect=[
                ToolExecution('{"status":"ok","data":{"project_id":"FY25-BAIYA_600MW"}}', "ok"),
                ToolExecution('{"status":"ok","data":{"duration_percent_complete":61.2}}', "ok"),
            ],
        ):
            result = graph.invoke(state)

        routed_tools = ToolBindingCaptureFakeModel.bound_tool_sets[-1]
        self.assertIn("portfolio_resolve_project_id", routed_tools)
        self.assertIn("p6_get_project_summary", routed_tools)
        self.assertNotIn("sap_get_po_summary", routed_tools)
        self.assertNotIn("tc_search_lines", routed_tools)
        self.assertLess(len(routed_tools), len(ToolBindingCaptureFakeModel.bound_tool_sets[0]))
        self.assertEqual(
            result["tool_names"],
            ["portfolio_resolve_project_id", "p6_get_project_summary"],
        )

    def test_empty_final_answer_is_repaired_once(self):
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content=""),
            AIMessage(
                content=conversational_answer("repaired answer"),
                response_metadata={"model_name": "fallback/model"},
            ),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        result = graph.invoke(graph_input("user-a", 1, 2, "answer me"))
        self.assertIn("repaired answer", result["messages"][-1].content)
        self.assertEqual(result["model_name"], "fallback/model")

    def test_overproduced_status_answer_is_rewritten_without_tools(self):
        verbose_answer = """# Project Status

| Metric | Value |
|---|---|
| Progress | 61.2% |
| Forecast finish | 29 March 2027 |

## Schedule
The project is approximately 12 months behind its 26 March 2026 baseline finish.

## Key Observations
SPI and CPI are unavailable.

## Suggested Next Steps
Generate a chart and run another forecast. Would you like me to do that?"""
        concise_answer = (
            "The project is 61.2% complete and is forecast to finish on 29 March 2027, "
            "approximately 12 months after its 26 March 2026 baseline finish. SPI and CPI "
            "are unavailable."
        )
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content=verbose_answer),
            AIMessage(content=concise_answer),
        ]))
        graph = build_chat_graph(model, context_window=32_768)

        result = graph.invoke(graph_input(
            "user-a",
            1,
            2,
            "What is the current progress of the BAIYA solar project as of today?",
        ))

        self.assertEqual(result["messages"][-1].content, concise_answer)

    def test_explicit_detailed_table_request_is_not_rewritten(self):
        detailed_answer = """# Detailed Project Status

| Metric | Value |
|---|---|
| Progress | 61.2% |
| Forecast finish | 29 March 2027 |

## Schedule Analysis
The requested detailed schedule analysis is included here."""
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content=detailed_answer),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        state = graph_input(
            "user-a",
            1,
            2,
            "Give me a detailed project analysis with a comparison table.",
        )
        state["tool_names"] = ["p6_get_project_summary"]

        result = graph.invoke(state)

        self.assertEqual(result["messages"][-1].content, detailed_answer)

    def test_operational_answer_without_evidence_retries_with_full_catalog(self):
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content="The project is 50% complete."),
            AIMessage(content="", tool_calls=[{
                "name": "p6_get_project_summary",
                "args": {"project_id": "FY25-BAIYA_600MW"},
                "id": "call-1",
            }]),
            AIMessage(content="The project is 61.2% complete as of 11 July 2026."),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        state = graph_input(
            "user-a",
            1,
            2,
            "What is the current progress of FY25-BAIYA_600MW?",
        )
        state["run_id"] = "a" * 32

        with patch("engine.graph.builder._ensure_run_active", return_value=None), patch(
            "engine.graph.builder.execute_authenticated_tool",
            return_value=ToolExecution(
                '{"status":"ok","data":{"duration_percent_complete":61.2}}',
                "ok",
            ),
        ):
            result = graph.invoke(state)

        self.assertEqual(result["tool_names"], ["p6_get_project_summary"])
        self.assertEqual(
            result["messages"][-1].content,
            "The project is 61.2% complete as of 11 July 2026.",
        )

    def test_comparison_chart_bundle_adds_multiple_visualizations(self):
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content="", tool_calls=[{
                "name": "render_chart",
                "args": {
                    "chart_type": "project_comparison",
                    "project_ids": ["P-1", "P-2"],
                },
                "id": "chart-1",
            }]),
            AIMessage(content="The comparison dashboard highlights progress, activity mix, duration, and baseline slip."),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        state = graph_input("user-a", 1, 2, "Compare P-1 and P-2 and give me a proper report")
        state["run_id"] = "a" * 32
        charts = tuple({
            "schema_version": "visualization.v1",
            "chart_type": f"comparison-{index}",
            "title": f"Chart {index}",
            "spec": {"schema_version": "visualization.v1", "chart_id": f"chart-{index}"},
        } for index in range(4))
        with patch("engine.graph.builder._ensure_run_active", return_value=None), patch(
            "engine.graph.builder.execute_authenticated_tool",
            return_value=ToolExecution(
                '{"status":"ok","data":{"chart_count":4}}',
                "ok",
                visualizations=charts,
            ),
        ):
            result = graph.invoke(state)
        self.assertEqual(len(result["visualizations"]), 4)
        self.assertEqual(result["visualizations"][3]["title"], "Chart 3")

    def test_repeated_empty_final_answer_fails_instead_of_completing_blank(self):
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content=""),
            AIMessage(content="   "),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        with self.assertRaises(InvalidModelResponse):
            graph.invoke(graph_input("user-a", 1, 2, "answer me"))

    def test_registered_raw_tool_markup_is_normalized_and_executed(self):
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content=(
                "<tool_call><function=p6_get_activities>"
                "<parameter=project_id>FY26-P18</parameter>"
                "<parameter=status>in_progress</parameter>"
                "<parameter=limit>100</parameter></function></tool_call>"
            )),
            AIMessage(content="There are 84 in-progress activities; here are the available details."),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        state = graph_input("user-a", 1, 2, "which activities are in progress?")
        state["run_id"] = "a" * 32
        with patch("engine.graph.builder._ensure_run_active", return_value=None), patch(
            "engine.graph.builder.execute_authenticated_tool",
            return_value=ToolExecution('{"status":"ok","data":{"total_matching":84}}', "ok"),
        ) as execute:
            result = graph.invoke(state)
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[0], "p6_get_activities")
        self.assertEqual(execute.call_args.args[1], {
            "project_id": "FY26-P18",
            "limit": 100,
            "status": "in_progress",
            "offset": 0,
        })
        self.assertEqual(result["tool_names"], ["p6_get_activities"])
        self.assertEqual(
            result["messages"][-1].content,
            "There are 84 in-progress activities; here are the available details.",
        )

    def test_repeated_raw_tool_markup_fails_after_repair(self):
        raw_markup = "<tool_call><function=p6_get_activities></function></tool_call>"
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content=raw_markup),
            AIMessage(content=raw_markup),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        with self.assertRaises(InvalidModelResponse):
            graph.invoke(graph_input("user-a", 1, 2, "which activities are in progress?"))

    def test_raw_tool_parser_rejects_unknown_tools_and_extra_prose(self):
        self.assertIsNone(parse_raw_tool_call(
            "<tool_call><function=unknown_tool></function></tool_call>"
        ))
        self.assertIsNone(parse_raw_tool_call(
            "I will check. <tool_call><function=tc_get_network_summary></function></tool_call>"
        ))

    def test_malformed_raw_markup_gets_one_tool_enabled_retry(self):
        malformed = "<tool_call><function=unknown_tool></function></tool_call>"
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content=malformed),
            AIMessage(content="", tool_calls=[{
                "name": "portfolio_resolve_project_id",
                "args": {"name": "ASEJ6PL_S07_FT_300MW_PPA"},
                "id": "call-1",
            }]),
            AIMessage(content="The project risk data is unavailable."),
            AIMessage(content="The project risk data is unavailable."),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        state = graph_input("user-a", 1, 2, "why is ASEJ6PL_S07_FT_300MW_PPA at risk?")
        state["run_id"] = "a" * 32
        with patch("engine.graph.builder._ensure_run_active", return_value=None), patch(
            "engine.graph.builder.execute_authenticated_tool",
            return_value=ToolExecution('{"status":"no_data","data":{}}', "no_data"),
        ):
            result = graph.invoke(state)
        self.assertEqual(result["tool_names"], ["portfolio_resolve_project_id"])
        self.assertEqual(result["messages"][-1].content, "The project risk data is unavailable.")

    def test_interrupted_thread_reset_deletes_incomplete_checkpoint(self):
        service = ChatGraphService()
        deleted = []
        service.checkpointer = type("Saver", (), {
            "delete_thread": lambda _self, thread_id: deleted.append(thread_id),
        })()
        service.reset_interrupted_thread("thread")
        self.assertEqual(deleted, ["thread"])

    def test_agent_subgraph_executes_tool_call_and_preserves_result_group(self):
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content="", tool_calls=[{
                "name": "tc_get_network_summary",
                "args": {},
                "id": "call-1",
            }]),
            AIMessage(content=""),
            AIMessage(content=conversational_answer("final answer")),
        ]))
        graph = build_chat_graph(model, context_window=32_768)
        state = graph_input("user-a", 1, 2, "network status")
        state["run_id"] = "a" * 32
        with patch("engine.graph.builder._ensure_run_active", return_value=None), patch(
            "engine.graph.builder.execute_authenticated_tool",
            return_value=ToolExecution(
                '{"status":"ok","data":{}}',
                "ok",
                evidence=({
                    "evidence_id": "tc-1",
                    "tool_name": "tc_get_network_summary",
                    "status": "ok",
                    "source_system": "TC",
                    "source_entity": "tc_network_edge",
                },),
            ),
        ):
            result = graph.invoke(state)

        self.assertEqual(result["tool_names"], ["tc_get_network_summary"])
        self.assertEqual(result["evidence"][0]["tool_call_id"], "call-1")
        self.assertEqual(result["evidence"][0]["source_entity"], "tc_network_edge")
        self.assertEqual(result["messages"][-2].tool_call_id, "call-1")
        self.assertEqual(result["messages"][-1].content, "final answer")

    def test_parent_graph_resumes_same_thread_from_checkpointer(self):
        saver = InMemorySaver()
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content=conversational_answer("first answer")),
            AIMessage(content=conversational_answer("second answer")),
        ]))
        graph = build_chat_graph(model, saver, context_window=32_768)
        config = {"configurable": {"thread_id": "thread"}}

        first = graph.invoke(graph_input("user-a", 1, 2, "first"), config=config)
        second = graph.invoke(graph_input("user-a", 3, 4, "second"), config=config)

        self.assertEqual(first["turn_status"], "completed")
        message_ids = {message.id for message in second["messages"]}
        self.assertIn("chat-message:1", message_ids)
        self.assertIn("chat-message:2", message_ids)
        self.assertIn("chat-message:3", message_ids)
        self.assertIn("chat-message:4", message_ids)

    def test_checkpoint_owner_binding_fails_closed(self):
        saver = InMemorySaver()
        model = ToolCapableFakeModel(messages=iter([
            AIMessage(content=conversational_answer("first answer")),
            AIMessage(content=conversational_answer("must not be returned")),
        ]))
        graph = build_chat_graph(model, saver, context_window=32_768)
        config = {"configurable": {"thread_id": "thread"}}
        graph.invoke(graph_input("user-a", 1, 2, "first"), config=config)

        with self.assertRaises(PermissionError):
            graph.invoke(graph_input("user-b", 3, 4, "hijack"), config=config)


if __name__ == "__main__":
    unittest.main()
