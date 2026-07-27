import os
import sys
from pathlib import Path
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from engine.graph.context_policy import (
    ContextBudget,
    bound_recent_messages,
    build_compaction_plan,
    group_complete_turns,
    tool_groups_are_complete,
)


class ContextPolicyTests(unittest.TestCase):
    def test_groups_tool_call_and_all_results_inside_one_turn(self):
        messages = [
            HumanMessage(content="first"),
            AIMessage(content="", tool_calls=[{"name": "a", "args": {}, "id": "call-1"}]),
            ToolMessage(content="result", tool_call_id="call-1"),
            AIMessage(content="answer"),
            HumanMessage(content="second"),
            AIMessage(content="answer two"),
        ]
        turns = group_complete_turns(messages)
        self.assertEqual(len(turns), 2)
        self.assertEqual(len(turns[0]), 4)
        self.assertTrue(tool_groups_are_complete(turns[0]))

    def test_detects_orphaned_or_unanswered_tool_messages(self):
        unanswered = [
            AIMessage(content="", tool_calls=[{"name": "a", "args": {}, "id": "call-1"}]),
        ]
        orphaned = [ToolMessage(content="result", tool_call_id="call-1")]
        self.assertFalse(tool_groups_are_complete(unanswered))
        self.assertFalse(tool_groups_are_complete(orphaned))

    def test_compaction_retains_four_complete_recent_turns(self):
        messages = []
        for index in range(6):
            messages.extend([
                HumanMessage(content=f"question {index} " + ("x" * 5_000)),
                AIMessage(content=f"answer {index}"),
            ])
        plan = build_compaction_plan(
            messages,
            ContextBudget(
                context_window=12_000,
                output_reserve=1_000,
                system_and_tools_reserve=1_000,
            ),
        )
        self.assertIsNotNone(plan)
        self.assertEqual(len(group_complete_turns(plan.messages_to_keep)), 4)
        self.assertEqual(len(group_complete_turns(plan.messages_to_summarize)), 2)

    def test_payload_bounding_does_not_break_tool_group_structure(self):
        messages = [
            HumanMessage(content="q" * 500),
            AIMessage(content="", tool_calls=[{"name": "a", "args": {}, "id": "call-1"}]),
            ToolMessage(content="r" * 500, tool_call_id="call-1"),
            AIMessage(content="done"),
        ]
        bounded = bound_recent_messages(messages, 100)
        self.assertTrue(tool_groups_are_complete(bounded))
        self.assertIn("truncated", bounded[0].content)
        self.assertIn("truncated", bounded[2].content)


if __name__ == "__main__":
    unittest.main()
