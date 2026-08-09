import os
import sys
from pathlib import Path
import unittest
from unittest.mock import Mock, patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.graph.service import build_graph_model, resolve_model_context_window
from engine.agent import _openrouter_request_options
from engine.openrouter_config import (
    DEFAULT_OPENROUTER_FALLBACK_MODELS,
    OpenRouterChatModel,
    openrouter_extra_body,
    openrouter_fallback_models,
)
from langchain_core.messages import HumanMessage


class OpenRouterFallbackTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {"DATABASE_URL": "sqlite:///:memory:"},
            clear=True,
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_requested_models_are_the_default_ordered_fallbacks(self):
        with patch.dict(os.environ, {"OPENROUTER_MODEL": "primary/model"}, clear=False):
            os.environ.pop("OPENROUTER_FALLBACK_MODELS", None)
            self.assertEqual(
                openrouter_fallback_models(),
                list(DEFAULT_OPENROUTER_FALLBACK_MODELS),
            )
            self.assertEqual(openrouter_extra_body(), {
                "models": list(DEFAULT_OPENROUTER_FALLBACK_MODELS),
                "provider": {"require_parameters": True},
            })

    def test_custom_fallbacks_are_deduplicated_and_blank_disables_them(self):
        with patch.dict(os.environ, {
            "OPENROUTER_MODEL": "primary/model",
            "OPENROUTER_FALLBACK_MODELS": "fallback/a, primary/model, fallback/a, fallback/b",
        }):
            self.assertEqual(openrouter_fallback_models(), ["fallback/a", "fallback/b"])
        with patch.dict(os.environ, {
            "OPENROUTER_MODEL": "primary/model",
            "OPENROUTER_FALLBACK_MODELS": "",
        }):
            self.assertEqual(openrouter_fallback_models(), [])

    def test_graph_model_sends_openrouter_native_fallback_body(self):
        with patch.dict(os.environ, {
            "AI_PROVIDER": "openrouter",
            "OPENROUTER_MODEL": "primary/model",
            "OPENROUTER_FALLBACK_MODELS": "fallback/a,fallback/b",
            "OPENROUTER_API_KEY": "test-key",
        }):
            model = build_graph_model()
        self.assertEqual(model.extra_body, {
            "models": ["fallback/a", "fallback/b"],
            "provider": {"require_parameters": True},
        })
        self.assertIsInstance(model, OpenRouterChatModel)

    def test_openrouter_adapter_sends_supported_max_tokens_parameter(self):
        model = OpenRouterChatModel(
            model="primary/model",
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            max_completion_tokens=2048,
            extra_body={"provider": {"require_parameters": True}},
        )
        payload = model._get_request_payload([HumanMessage(content="hello")])
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertNotIn("max_completion_tokens", payload)

    def test_legacy_agent_wraps_fallbacks_as_openai_extra_body(self):
        with patch.dict(os.environ, {
            "AI_PROVIDER": "openrouter",
            "OPENROUTER_MODEL": "primary/model",
            "OPENROUTER_FALLBACK_MODELS": "fallback/a,fallback/b",
        }):
            self.assertEqual(_openrouter_request_options(), {
                "extra_body": {
                    "models": ["fallback/a", "fallback/b"],
                    "provider": {"require_parameters": True},
                },
            })

    def test_context_budget_uses_smallest_valid_fallback_window(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": [
            {"id": "primary/model", "context_length": 131_072, "supported_parameters": ["tools", "tool_choice", "response_format"]},
            {"id": "fallback/a", "context_length": 65_536, "supported_parameters": ["tools", "tool_choice", "response_format"]},
            {"id": "fallback/b", "context_length": 262_144, "supported_parameters": ["tools", "tool_choice", "response_format"]},
        ]}
        model = type("Model", (), {"profile": None})()
        with patch.dict(os.environ, {
            "OPENROUTER_MODEL": "primary/model",
            "OPENROUTER_FALLBACK_MODELS": "fallback/a,fallback/b",
            "OPENROUTER_API_KEY": "test-key",
        }, clear=False), patch("requests.get", return_value=response):
            self.assertEqual(resolve_model_context_window(model, "openrouter"), 65_536)

    def test_model_without_tool_support_fails_startup_validation(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"data": [
            {"id": "primary/model", "context_length": 131_072, "supported_parameters": ["tools", "tool_choice", "response_format"]},
            {"id": "fallback/no-tools", "context_length": 65_536, "supported_parameters": ["temperature"]},
        ]}
        model = type("Model", (), {"profile": None})()
        with patch.dict(os.environ, {
            "OPENROUTER_MODEL": "primary/model",
            "OPENROUTER_FALLBACK_MODELS": "fallback/no-tools",
            "OPENROUTER_API_KEY": "test-key",
        }, clear=False), patch("requests.get", return_value=response):
            with self.assertRaises(RuntimeError):
                resolve_model_context_window(model, "openrouter")

if __name__ == "__main__":
    unittest.main()
