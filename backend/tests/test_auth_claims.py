import sys
from pathlib import Path
import unittest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from auth_claims import ClaimsValidationError, identity_from_claims


BASE_CLAIMS = {
    "tid": "tenant-1",
    "oid": "user-1",
    "name": "Akasha User",
    "preferred_username": "user@example.com",
}


def identity(claims):
    return identity_from_claims(
        claims,
        tenant_id="tenant-1",
        ceo_app_role="Akasha.CEO",
        pmag_app_role="Akasha.PMAG",
        ceo_group_id="ceo-group",
        pmag_group_id="pmag-group",
    )


class IdentityClaimTests(unittest.TestCase):
    def test_maps_ceo_app_role(self):
        result = identity({**BASE_CLAIMS, "roles": ["Akasha.CEO"]})
        self.assertEqual(result.role, "executive")
        self.assertEqual(result.subject, "user-1")
        self.assertEqual(result.email, "user@example.com")

    def test_maps_pmag_group(self):
        result = identity({**BASE_CLAIMS, "groups": ["pmag-group"]})
        self.assertEqual(result.role, "pmag")

    def test_ceo_role_takes_precedence_when_both_are_assigned(self):
        result = identity({**BASE_CLAIMS, "roles": ["Akasha.CEO", "Akasha.PMAG"]})
        self.assertEqual(result.role, "executive")

    def test_rejects_wrong_tenant(self):
        with self.assertRaises(ClaimsValidationError):
            identity({**BASE_CLAIMS, "tid": "other", "roles": ["Akasha.CEO"]})

    def test_rejects_missing_object_id(self):
        with self.assertRaises(ClaimsValidationError):
            identity({"tid": "tenant-1", "roles": ["Akasha.CEO"]})

    def test_rejects_user_without_supported_role(self):
        with self.assertRaises(ClaimsValidationError):
            identity({**BASE_CLAIMS, "roles": ["Unrelated.Role"]})

    def test_rejects_group_overage_without_inline_groups(self):
        with self.assertRaises(ClaimsValidationError):
            identity({**BASE_CLAIMS, "roles": [], "_claim_names": {"groups": "src1"}})

    def test_app_role_remains_authoritative_when_groups_are_over_limit(self):
        result = identity({
            **BASE_CLAIMS,
            "roles": ["Akasha.CEO"],
            "_claim_names": {"groups": "src1"},
        })
        self.assertEqual(result.role, "executive")


if __name__ == "__main__":
    unittest.main()
