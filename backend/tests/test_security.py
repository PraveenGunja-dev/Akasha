import os
import sys
from pathlib import Path
from unittest.mock import patch
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
import security


class _SigningKey:
    key = "test-key"


class _JwksClient:
    def get_signing_key_from_jwt(self, token):
        return _SigningKey()


class EntraSecurityTests(unittest.TestCase):
    def setUp(self):
        os.environ["AKASHA_AUTH_MODE"] = "entra"
        os.environ["ENTRA_TENANT_ID"] = "tenant-1"
        os.environ["ENTRA_CLIENT_ID"] = "api-client"
        os.environ.pop("ENTRA_AUDIENCE", None)
        security.get_entra_settings.cache_clear()
        security.get_auth_mode.cache_clear()

    def credentials(self):
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-token")

    def test_rejects_missing_bearer_token(self):
        with self.assertRaises(HTTPException) as raised:
            security.get_current_user(None)
        self.assertEqual(raised.exception.status_code, 401)

    @patch.object(security, "_jwks_client", return_value=_JwksClient())
    @patch.object(security.jwt, "decode")
    def test_verified_token_maps_to_identity(self, decode, _client):
        decode.return_value = {
            "tid": "tenant-1",
            "oid": "user-1",
            "preferred_username": "user@example.com",
            "name": "User",
            "roles": ["Akasha.PMAG"],
        }
        user = security.get_current_user(self.credentials())
        self.assertEqual(user.subject, "user-1")
        self.assertEqual(user.role, "pmag")
        decode.assert_called_once()

    @patch.object(security, "_jwks_client", return_value=_JwksClient())
    @patch.object(security.jwt, "decode", side_effect=security.jwt.InvalidTokenError())
    def test_invalid_signed_token_is_sanitized(self, _decode, _client):
        with self.assertRaises(HTTPException) as raised:
            security.get_current_user(self.credentials())
        self.assertEqual(raised.exception.status_code, 401)
        self.assertNotIn("signed-token", str(raised.exception.detail))

    def test_role_dependency_rejects_wrong_role(self):
        dependency = security.require_roles("executive")
        pmag = security.AuthenticatedIdentity(
            "user", "tenant-1", "u@example.com", "User", "u@example.com", "pmag"
        )
        with self.assertRaises(HTTPException) as raised:
            dependency(pmag)
        self.assertEqual(raised.exception.status_code, 403)

    def test_development_mode_accepts_bounded_role_identity(self):
        os.environ["AKASHA_AUTH_MODE"] = "development"
        security.get_auth_mode.cache_clear()
        user = security.get_current_user(
            None,
            development_user="12345678-abcd",
            development_role="executive",
        )
        self.assertEqual(user.subject, "dev:12345678-abcd")
        self.assertEqual(user.tenant_id, "development")
        self.assertEqual(user.role, "executive")

    def test_development_mode_rejects_invalid_role_or_user(self):
        os.environ["AKASHA_AUTH_MODE"] = "development"
        security.get_auth_mode.cache_clear()
        with self.assertRaises(HTTPException):
            security.get_current_user(None, development_user="short", development_role="executive")
        with self.assertRaises(HTTPException):
            security.get_current_user(None, development_user="12345678", development_role="admin")


if __name__ == "__main__":
    unittest.main()
