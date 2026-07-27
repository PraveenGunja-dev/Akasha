import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from engine.graph.builder import InvalidModelResponse, build_chat_graph
from engine.graph.service import ChatGraphService
from engine.graph.tools import ToolExecution, parse_raw_tool_call


class ToolCapableFakeModel(GenericFakeChatModel):
    def bind_tools(self, _tools, **_kwargs):
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
            return_value=ToolExecution('{"status":"ok","data":{}}', "ok"),
        ):
            result = graph.invoke(state)

        self.assertEqual(result["tool_names"], ["tc_get_network_summary"])
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
