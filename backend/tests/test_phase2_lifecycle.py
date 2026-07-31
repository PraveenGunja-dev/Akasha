import os
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AKASHA_CHAT_ENGINE"] = "legacy"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth_claims import AuthenticatedIdentity
from database import Base, get_db
import models
from routers import ai, chat_sessions
from security import get_current_user


USER_A = AuthenticatedIdentity("phase2-a", "tenant", "a@example.com", "A", "a@example.com", "executive")
USER_B = AuthenticatedIdentity("phase2-b", "tenant", "b@example.com", "B", "b@example.com", "pmag")


class Phase2LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        cls.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
        cls.user = USER_A
        app = FastAPI()
        app.include_router(chat_sessions.router)
        app.include_router(ai.router)

        def db_override():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: cls.user
        cls.client = TestClient(app)

    def setUp(self):
        type(self).user = USER_A
        db = self.Session()
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
        db.close()

    def create_session(self):
        return self.client.post("/api/chat/sessions", json={"title": "Phase 2"}).json()["session_id"]

    def test_stream_failure_is_terminal_and_persisted(self):
        session_id = self.create_session()

        def failing_stream(**_kwargs):
            yield "partial"
            raise RuntimeError("provider secret must not escape")

        with patch.object(ai.orchestrator, "process_message_stream", failing_stream):
            response = self.client.post("/api/chat", json={"message": "fail", "sessionId": session_id})

        self.assertIn('"type": "error"', response.text)
        self.assertIn('"status": "failed"', response.text)
        self.assertNotIn("provider secret", response.text)
        db = self.Session()
        try:
            run = db.query(models.ChatRun).one()
            assistant = db.query(models.ChatMessage).filter(models.ChatMessage.role == "assistant").one()
            self.assertEqual(run.status, "failed")
            self.assertEqual(assistant.status, "failed")
            self.assertEqual(assistant.content, "")
        finally:
            db.close()

    def test_cancel_endpoint_is_owner_checked_and_idempotent(self):
        session_id = self.create_session()
        db = self.Session()
        try:
            user_message = models.ChatMessage(session_id=session_id, role="user", content="q", status="completed")
            assistant = models.ChatMessage(session_id=session_id, role="assistant", content="", status="running")
            db.add_all([user_message, assistant])
            db.flush()
            run = models.ChatRun(
                run_id="a" * 32,
                session_id=session_id,
                user_message_id=user_message.id,
                assistant_message_id=assistant.id,
                request_id="request",
                engine="legacy",
                status="running",
            )
            db.add(run)
            db.commit()
        finally:
            db.close()

        type(self).user = USER_B
        self.assertEqual(self.client.post(f"/api/chat/runs/{'a' * 32}/cancel").status_code, 404)
        type(self).user = USER_A
        first = self.client.post(f"/api/chat/runs/{'a' * 32}/cancel")
        second = self.client.post(f"/api/chat/runs/{'a' * 32}/cancel")
        self.assertEqual(first.json()["status"], "cancel_requested")
        self.assertEqual(second.json()["status"], "cancel_requested")

    def test_stream_success_exposes_run_and_completed_message_status(self):
        session_id = self.create_session()

        def successful_stream(**_kwargs):
            _kwargs["evidence_out"].append({
                "evidence_id": "p6-1",
                "tool_call_id": "call-1",
                "tool_name": "p6_get_project_summary",
                "status": "ok",
                "source_system": "P6",
                "source_entity": "p6_project",
                "project_id": "P-1",
                "record_ids": [],
                "data_as_of": None,
                "last_synced_at": None,
            })
            yield "answer"
            yield {"type": "metadata", "response": SimpleNamespace(
                content="answer",
                intent_type="deep_analysis",
                project_ids=[],
                domains=[],
                data_as_of=None,
                sources_used=[],
                latency_ms=1,
            )}

        with patch.object(ai.orchestrator, "process_message_stream", successful_stream):
            response = self.client.post("/api/chat", json={"message": "ok", "sessionId": session_id})
        self.assertIn('"stream_version": "2.0"', response.text)
        self.assertIn('"run_id":', response.text)
        detail = self.client.get(f"/api/chat/sessions/{session_id}").json()
        self.assertEqual([message["status"] for message in detail["messages"]], ["completed", "completed"])
        assistant = detail["messages"][1]
        self.assertEqual(assistant["metadata"]["sources"], ["p6_project"])
        self.assertEqual(assistant["metadata"]["provenance"]["tables"], ["p6_project"])
        self.assertEqual(assistant["metadata"]["evidence"][0]["tool_call_id"], "call-1")


if __name__ == "__main__":
    unittest.main()
