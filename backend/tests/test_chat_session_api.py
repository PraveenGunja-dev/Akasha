import os
import sys
from pathlib import Path
import unittest


os.environ["DATABASE_URL"] = "sqlite:///:memory:"
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
from routers import chat_sessions
from security import get_current_user


USER_A = AuthenticatedIdentity("api-user-a", "tenant", "a@example.com", "User A", "a@example.com", "executive")
USER_B = AuthenticatedIdentity("api-user-b", "tenant", "b@example.com", "User B", "b@example.com", "pmag")


class ChatSessionApiTests(unittest.TestCase):
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

    def setUp(self):
        self.user = USER_A
        type(self).user = USER_A
        db = self.Session()
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()
        db.close()

    def test_create_list_read_rename_and_delete_owned_session(self):
        created = self.client.post("/api/chat/sessions", json={"title": "Initial"})
        self.assertEqual(created.status_code, 201)
        session_id = created.json()["session_id"]
        self.assertRegex(session_id, r"^[a-f0-9]{32}$")

        listed = self.client.get("/api/chat/sessions")
        self.assertEqual([item["session_id"] for item in listed.json()], [session_id])

        renamed = self.client.patch(f"/api/chat/sessions/{session_id}", json={"title": "Renamed"})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["title"], "Renamed")

        detail = self.client.get(f"/api/chat/sessions/{session_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["messages"], [])

        deleted = self.client.delete(f"/api/chat/sessions/{session_id}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get(f"/api/chat/sessions/{session_id}").status_code, 404)

    def test_cross_user_access_is_hidden(self):
        created = self.client.post("/api/chat/sessions", json={"title": "User A"}).json()
        type(self).user = USER_B
        self.assertEqual(self.client.get("/api/chat/sessions").json(), [])
        self.assertEqual(
            self.client.get(f"/api/chat/sessions/{created['session_id']}").status_code,
            404,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/chat/sessions/{created['session_id']}",
                json={"title": "Hijacked"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(f"/api/chat/sessions/{created['session_id']}").status_code,
            404,
        )

    def test_session_history_is_paginated_without_hiding_older_chats(self):
        created_ids = []
        for index in range(5):
            response = self.client.post("/api/chat/sessions", json={"title": f"Chat {index}"})
            created_ids.append(response.json()["session_id"])

        first_page = self.client.get("/api/chat/sessions?skip=0&limit=2")
        second_page = self.client.get("/api/chat/sessions?skip=2&limit=2")
        final_page = self.client.get("/api/chat/sessions?skip=4&limit=2")

        self.assertEqual(
            [item["session_id"] for item in first_page.json()],
            list(reversed(created_ids))[:2],
        )
        self.assertEqual(
            [item["session_id"] for item in second_page.json()],
            list(reversed(created_ids))[2:4],
        )
        self.assertEqual(
            [item["session_id"] for item in final_page.json()],
            list(reversed(created_ids))[4:],
        )
        self.assertEqual(self.client.get("/api/chat/sessions?limit=201").status_code, 422)

    def test_legacy_import_is_private_and_resumable(self):
        imported = self.client.post("/api/chat/sessions/legacy-import", json={
            "title": "Imported",
            "messages": [
                {"type": "user", "content": "Question"},
                {"type": "bot", "content": "Answer"},
            ],
        })
        self.assertEqual(imported.status_code, 201)
        detail = self.client.get(
            f"/api/chat/sessions/{imported.json()['session_id']}"
        ).json()
        self.assertEqual([item["role"] for item in detail["messages"]], ["user", "assistant"])
        type(self).user = USER_B
        self.assertEqual(
            self.client.get(f"/api/chat/sessions/{detail['session_id']}").status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
