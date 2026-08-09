import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.graph.service import (
    configured_chat_engine,
    resolve_model_context_window,
    select_chat_engine,
)


class SessionStub:
    session_id = "a" * 32
    chat_engine = None


class RolloutTests(unittest.TestCase):
    def test_context_window_uses_selected_model_profile(self):
        model = type("Model", (), {"profile": {"max_input_tokens": 128_000}})()
        self.assertEqual(resolve_model_context_window(model, "azure"), 128_000)

    def test_context_window_environment_value_cannot_override_model_metadata(self):
        model = type("Model", (), {"profile": {"max_input_tokens": 128_000}})()
        with patch.dict(os.environ, {"AKASHA_MODEL_CONTEXT_WINDOW": "65536"}):
            self.assertEqual(resolve_model_context_window(model, "azure"), 128_000)

    def test_unknown_model_context_fails_instead_of_assuming_a_default(self):
        model = type("Model", (), {"profile": None})()
        with self.assertRaises(RuntimeError):
            resolve_model_context_window(model, "azure")

    def test_legacy_is_an_immediate_kill_switch(self):
        session = SessionStub()
        session.chat_engine = "langgraph"
        with patch.dict(os.environ, {"AKASHA_CHAT_ENGINE": "legacy"}):
            self.assertEqual(select_chat_engine(session, "tenant", "user"), "legacy")

    def test_canary_assignment_is_stable_on_session(self):
        session = SessionStub()
        session.chat_engine = None
        with patch.dict(os.environ, {
            "AKASHA_CHAT_ENGINE": "canary",
            "AKASHA_LANGGRAPH_ROLLOUT_PERCENT": "50",
        }):
            first = select_chat_engine(session, "tenant", "user")
            second = select_chat_engine(session, "tenant", "different-user")
        self.assertIn(first, {"legacy", "langgraph"})
        self.assertEqual(first, second)

    def test_invalid_engine_configuration_fails_closed(self):
        with patch.dict(os.environ, {"AKASHA_CHAT_ENGINE": "v2"}):
            with self.assertRaises(ValueError):
                configured_chat_engine()


if __name__ == "__main__":
    unittest.main()
