import ast
import hashlib
import json
import logging
import sys
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import Mock


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.observability import (  # noqa: E402
    log_observability_event,
    resolve_request_id,
    safe_exception_trace,
    serialize_sse_event,
)


class RequestIdTests(unittest.TestCase):
    def test_replaces_all_incoming_ids_with_server_uuid(self):
        for request_id in (
            None,
            "",
            "a",
            "REQ-123:part_2.0",
            "AKASHA_SECRET_TOKEN_123",
            "A" * 64,
            "bad/slash",
            "line\nbreak",
        ):
            with self.subTest(request_id=request_id):
                resolved = resolve_request_id(request_id)
                self.assertNotEqual(resolved, request_id)
                self.assertEqual(str(uuid.UUID(resolved)), resolved)

    def test_pattern_valid_secret_never_becomes_returned_or_logged_id(self):
        incoming_request_id = "AKASHA_SECRET_TOKEN_123"
        operational_request_id = resolve_request_id(incoming_request_id)
        logger = Mock()

        log_observability_event(
            logger,
            "chat_started",
            request_id=operational_request_id,
            session_id="session-2",
            elapsed_ms=0,
            response_intent="deep_analysis",
            tool_names=[],
        )
        frame = serialize_sse_event(
            "token", operational_request_id, content="answer"
        )
        serialized_log = logger.log.call_args.args[1]

        self.assertNotIn(incoming_request_id, operational_request_id)
        self.assertNotIn(incoming_request_id, serialized_log)
        self.assertNotIn(incoming_request_id, frame)
        self.assertEqual(json.loads(serialized_log)["request_id"], operational_request_id)
        self.assertEqual(json.loads(frame[len("data: ") :])["request_id"], operational_request_id)

    def test_chat_endpoint_does_not_bind_incoming_request_id_header(self):
        path = BACKEND_DIR / "routers/ai.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "chat_with_copilot"
        )
        argument_names = {argument.arg for argument in function.args.args}
        self.assertNotIn("x_request_id", argument_names)

        resolver_call = next(
            node
            for node in ast.walk(function)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "resolve_request_id"
        )
        self.assertEqual(resolver_call.args, [])
        self.assertEqual(resolver_call.keywords, [])


class SseSerializationTests(unittest.TestCase):
    def _decode(self, frame):
        self.assertTrue(frame.startswith("data: "))
        self.assertTrue(frame.endswith("\n\n"))
        self.assertEqual(len(frame.rstrip("\n").splitlines()), 1)
        return json.loads(frame[len("data: ") :])

    def test_serializes_correlated_event_as_one_sse_frame(self):
        event = self._decode(
            serialize_sse_event("token", "request-42", content="first line\nsecond line")
        )
        self.assertEqual(
            event,
            {
                "type": "token",
                "content": "first line\nsecond line",
                "request_id": "request-42",
            },
        )

    def test_serializes_non_json_metadata_without_breaking_correlation(self):
        event = self._decode(
            serialize_sse_event("metadata", "server-id", metadata={"data_as_of": date(2026, 7, 1)})
        )
        self.assertEqual(event["request_id"], "server-id")
        self.assertEqual(event["metadata"]["data_as_of"], "2026-07-01")

    def test_supports_each_phase_zero_event_shape(self):
        frames = [
            serialize_sse_event("token", "same-id", content="answer"),
            serialize_sse_event("visualization", "same-id", spec={"series": []}),
            serialize_sse_event("metadata", "same-id", metadata={"sources": ["p6"]}),
            serialize_sse_event(
                "error",
                "same-id",
                error={"code": "chat_stream_failed", "message": "sanitized"},
            ),
        ]
        events = [self._decode(frame) for frame in frames]
        self.assertEqual([event["type"] for event in events], ["token", "visualization", "metadata", "error"])
        self.assertEqual({event["request_id"] for event in events}, {"same-id"})


class PayloadSafeLoggingTests(unittest.TestCase):
    def test_exception_trace_contains_locations_but_not_exception_text(self):
        secret = "provider payload must not be logged"
        try:
            raise ValueError(secret)
        except ValueError as exc:
            trace = safe_exception_trace(exc)
        serialized = json.dumps(trace)
        self.assertEqual(trace[0]["error_type"], "ValueError")
        self.assertEqual(trace[0]["frames"][-1]["function"], self._testMethodName)
        self.assertNotIn(secret, serialized)

    def test_logs_only_supplied_operational_metadata(self):
        logger = Mock()
        raw_chat_payload = "sensitive question that must not be logged"
        operational_request_id = "123e4567-e89b-12d3-a456-426614174000"

        log_observability_event(
            logger,
            "chat_failed",
            request_id=operational_request_id,
            session_id="session-2",
            elapsed_ms=31,
            response_intent="deep_analysis",
            tool_names=["p6", "sap", "p6"],
            level=logging.ERROR,
            error_type="RuntimeError",
        )

        logger.log.assert_called_once()
        level, serialized = logger.log.call_args.args
        record = json.loads(serialized)
        self.assertEqual(level, logging.ERROR)
        self.assertEqual(
            record,
            {
                "event": "chat_failed",
                "request_id": operational_request_id,
                "session_id": "sha256:"
                + hashlib.sha256(b"session-2").hexdigest(),
                "elapsed_ms": 31,
                "response_intent": "deep_analysis",
                "tool_names": ["p6", "sap"],
                "error_type": "RuntimeError",
            },
        )
        self.assertNotIn(raw_chat_payload, serialized)
        self.assertFalse({"message", "history", "content", "payload"} & record.keys())

    def test_pseudonymizes_session_ids_and_unsafe_request_ids(self):
        logger = Mock()
        raw_session_id = "caller session\nwith secret text"
        raw_request_id = "AKASHA_SECRET_TOKEN_123"

        log_observability_event(
            logger,
            "chat_started",
            request_id=raw_request_id,
            session_id=raw_session_id,
            elapsed_ms=0,
            response_intent="deep_analysis",
            tool_names=[],
        )

        serialized = logger.log.call_args.args[1]
        record = json.loads(serialized)
        self.assertNotIn(raw_session_id, serialized)
        self.assertNotIn(raw_request_id, serialized)
        self.assertEqual(
            record["session_id"],
            "sha256:" + hashlib.sha256(raw_session_id.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            record["request_id"],
            "sha256:" + hashlib.sha256(raw_request_id.encode("utf-8")).hexdigest(),
        )
        self.assertLessEqual(len(record["session_id"]), 71)

    def test_vision_failure_handler_cannot_emit_provider_exception_text(self):
        path = BACKEND_DIR / "engine/agent.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "analyze_image_context"
        )
        handler = next(node for node in ast.walk(function) if isinstance(node, ast.ExceptHandler))
        self.assertIsNone(handler.name)

        log_call = next(
            node
            for node in ast.walk(handler)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "log_observability_event"
        )
        keyword_names = {keyword.arg for keyword in log_call.keywords if keyword.arg}
        self.assertTrue({"request_id", "operation", "status"} <= keyword_names)

        return_node = next(node for node in handler.body if isinstance(node, ast.Return))
        self.assertIsInstance(return_node.value, ast.Constant)
        self.assertEqual(return_node.value.value, "Image context extraction was unavailable.")

    def test_wave_one_call_sites_do_not_log_payload_keywords(self):
        forbidden = {
            "content",
            "history",
            "message",
            "payload",
            "prompt",
            "tool_args",
            "tool_output",
        }
        for relative_path in ("routers/ai.py", "engine/agent.py"):
            path = BACKEND_DIR / relative_path
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            calls = [
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "log_observability_event"
            ]
            self.assertTrue(calls, f"No observability calls found in {relative_path}")
            for call in calls:
                keyword_names = {keyword.arg for keyword in call.keywords if keyword.arg}
                self.assertFalse(
                    forbidden & keyword_names,
                    f"Sensitive observability field in {relative_path}:{call.lineno}",
                )


class ImportSafetyTests(unittest.TestCase):
    def test_pure_contract_does_not_import_main(self):
        self.assertNotIn("main", sys.modules)
        self.assertNotIn("backend.main", sys.modules)


if __name__ == "__main__":
    unittest.main()
