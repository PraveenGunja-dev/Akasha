import os
import sys
from pathlib import Path
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import httpx
import openai
from langgraph.errors import GraphRecursionError

from engine.provider_errors import classify_provider_error


def response(status: int) -> httpx.Response:
    request = httpx.Request("POST", "https://provider.invalid/chat")
    return httpx.Response(status, request=request)


class ProviderErrorTests(unittest.TestCase):
    def test_rate_limit_is_specific_and_does_not_echo_provider_text(self):
        exc = openai.RateLimitError(
            "secret provider quota details",
            response=response(429),
            body=None,
        )
        result = classify_provider_error(exc)
        self.assertEqual(result.code, "provider_rate_limited")
        self.assertNotIn("secret", result.message)

    def test_nested_provider_error_is_classified(self):
        provider_exc = openai.NotFoundError(
            "secret route details",
            response=response(404),
            body=None,
        )
        try:
            raise provider_exc
        except openai.NotFoundError as cause:
            try:
                raise RuntimeError("wrapper") from cause
            except RuntimeError as wrapper:
                result = classify_provider_error(wrapper)
        self.assertEqual(result.code, "provider_route_unavailable")

    def test_unknown_error_stays_generic(self):
        result = classify_provider_error(ValueError("internal details"))
        self.assertEqual(result.code, "chat_stream_failed")
        self.assertNotIn("internal", result.message)

    def test_graph_recursion_limit_has_actionable_safe_error(self):
        result = classify_provider_error(GraphRecursionError("internal graph details"))
        self.assertEqual(result.code, "agent_iteration_limit")
        self.assertIn("narrower scope", result.message)
        self.assertNotIn("internal", result.message)


if __name__ == "__main__":
    unittest.main()
