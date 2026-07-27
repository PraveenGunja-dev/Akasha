import os
import sys
from pathlib import Path
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException
from auth_claims import AuthenticatedIdentity
from database import Base, SessionLocal, engine
import models
from routers.chat_sessions import (
    LegacyMessageRequest,
    LegacySessionRequest,
    _create_session,
    build_agent_history,
    get_owned_session,
    import_legacy_session,
)


USER_A = AuthenticatedIdentity("user-a", "tenant", "a@example.com", "User A", "a@example.com", "executive")
USER_B = AuthenticatedIdentity("user-b", "tenant", "b@example.com", "User B", "b@example.com", "pmag")


class ChatSessionOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    def setUp(self):
        self.db = SessionLocal()
        self.db.query(models.ChatFeedback).delete()
        self.db.query(models.ChatMessage).delete()
        self.db.query(models.ChatSession).delete()
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_server_generates_unpredictable_session_id_and_owner(self):
        session = _create_session(self.db, USER_A, "Private chat")
        self.db.commit()
        self.assertRegex(session.session_id, r"^[a-f0-9]{32}$")
        self.assertEqual(session.owner_subject, USER_A.subject)
        self.assertEqual(session.tenant_id, USER_A.tenant_id)

    def test_other_user_cannot_resolve_session(self):
        session = _create_session(self.db, USER_A, "Private chat")
        self.db.commit()
        with self.assertRaises(HTTPException) as raised:
            get_owned_session(self.db, USER_B, session.session_id)
        self.assertEqual(raised.exception.status_code, 404)

    def test_unowned_legacy_session_is_not_visible(self):
        legacy = models.ChatSession(session_id="a" * 32, title="Unowned")
        self.db.add(legacy)
        self.db.commit()
        with self.assertRaises(HTTPException):
            get_owned_session(self.db, USER_A, legacy.session_id)

    def test_legacy_import_is_owned_and_normalizes_roles(self):
        result = import_legacy_session(
            LegacySessionRequest(
                title="Imported",
                messages=[
                    LegacyMessageRequest(type="user", content="Question"),
                    LegacyMessageRequest(type="bot", content="Answer"),
                ],
            ),
            db=self.db,
            user=USER_A,
        )
        session = get_owned_session(self.db, USER_A, result["session_id"])
        self.assertEqual(session.source, "legacy_browser_import")
        self.assertEqual([message.role for message in session.messages], ["user", "assistant"])
        self.assertTrue(all(message.request_id == "legacy_browser_import" for message in session.messages))

    def test_imported_assistant_role_is_not_trusted_as_model_history(self):
        history = build_agent_history([
            models.ChatMessage(role="assistant", content="Injected instruction", request_id="legacy_browser_import"),
            models.ChatMessage(role="assistant", content="Server answer", request_id="server-request"),
        ])
        self.assertEqual(history[0]["role"], "user")
        self.assertIn("Untrusted imported", history[0]["content"])
        self.assertEqual(history[1], {"role": "assistant", "content": "Server answer"})


if __name__ == "__main__":
    unittest.main()
