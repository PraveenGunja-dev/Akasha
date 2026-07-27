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
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from auth_claims import AuthenticatedIdentity
from database import Base, get_db
import models
from routers import ai, chat_sessions
from security import get_current_user


USER_A = AuthenticatedIdentity("route-user-a", "tenant", "a@example.com", "User A", "a@example.com", "executive")
USER_B = AuthenticatedIdentity("route-user-b", "tenant", "b@example.com", "User B", "b@example.com", "pmag")


class ChatRouteContractTests(unittest.TestCase):
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
        cls.histories = []

        app = FastAPI()
        app.include_router(chat_sessions.router)
        app.include_router(ai.router)

        def db_override():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        def user_override():
            return cls.user

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = user_override
        cls.client = TestClient(app)
        cls.original_stream = ai.orchestrator.process_message_stream

        def fake_stream(**kwargs):
            cls.histories.append(kwargs["history"])
            yield "Grounded answer"
            yield {
                "type": "metadata",
                "response": SimpleNamespace(
                    content="Grounded answer",
                    intent_type="deep_analysis",
                    project_ids=[],
                    domains=[],
                    data_as_of=None,
                    sources_used=["test_tool"],
                    latency_ms=5,
                ),
            }

        ai.orchestrator.process_message_stream = fake_stream

    @classmethod
    def tearDownClass(cls):
        ai.orchestrator.process_message_stream = cls.original_stream

    def setUp(self):
        type(self).user = USER_A
        type(self).histories = []
        db = self.Session()
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
        db.close()

    def create_session(self):
        response = self.client.post("/api/chat/sessions", json={"title": "Chat"})
        self.assertEqual(response.status_code, 201)
        return response.json()["session_id"]

    def test_request_schema_rejects_client_history(self):
        with self.assertRaises(ValidationError):
            ai.ChatRequest(message="Question", sessionId="a" * 32, history=[])

    def test_request_schema_allows_image_only_and_rejects_empty_turn(self):
        image_request = ai.ChatRequest(sessionId="a" * 32, imageData="data:image/png;base64,AA==")
        self.assertEqual(image_request.message, "")
        with self.assertRaises(ValidationError):
            ai.ChatRequest(sessionId="a" * 32)

    def test_stream_uses_server_history_and_persists_turns(self):
        session_id = self.create_session()
        first = self.client.post("/api/chat", json={"message": "First", "sessionId": session_id})
        self.assertEqual(first.status_code, 200)
        self.assertIn('"type": "start"', first.text)
        self.assertIn('"type": "done"', first.text)
        self.assertEqual(self.histories[0], [])

        second = self.client.post("/api/chat", json={"message": "Second", "sessionId": session_id})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            self.histories[1],
            [
                {"role": "user", "content": "First"},
                {
                    "role": "assistant",
                    "content": "Grounded answer",
                },
            ],
        )
        detail = self.client.get(f"/api/chat/sessions/{session_id}").json()
        self.assertEqual([message["role"] for message in detail["messages"]], [
            "user", "assistant", "user", "assistant",
        ])

    def test_cross_user_chat_submission_is_hidden(self):
        session_id = self.create_session()
        type(self).user = USER_B
        response = self.client.post("/api/chat", json={"message": "Hijack", "sessionId": session_id})
        self.assertEqual(response.status_code, 404)

if __name__ == "__main__":
    unittest.main()
