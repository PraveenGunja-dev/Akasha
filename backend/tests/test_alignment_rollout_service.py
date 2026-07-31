import os
import sys
from pathlib import Path
import unittest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services.alignment_rollout_service import select_alignment_cohort


class AlignmentRolloutServiceTests(unittest.TestCase):
    def test_canary_assignment_is_stable_and_server_owned(self):
        arguments = dict(
            tenant_id="tenant", user_id="user", session_id="session",
            mode="canary", rollout_percent=37, domains="schedule,sap",
        )
        first = select_alignment_cohort(**arguments)
        self.assertEqual(first, select_alignment_cohort(**arguments))
        self.assertEqual(first.enabled_domains, frozenset({"schedule", "sap"}))

    def test_zero_and_full_canary_percent_are_deterministic(self):
        identity = dict(tenant_id="t", user_id="u", session_id="s", mode="canary")
        self.assertEqual(select_alignment_cohort(**identity, rollout_percent=0).cohort, "legacy")
        self.assertEqual(select_alignment_cohort(**identity, rollout_percent=100).cohort, "aligned")

    def test_domain_kill_switch_and_invalid_configuration(self):
        decision = select_alignment_cohort(
            tenant_id="t", user_id="u", session_id="s", mode="aligned", domains="schedule",
        )
        self.assertTrue(decision.uses_aligned_domain("schedule"))
        self.assertFalse(decision.uses_aligned_domain("risk"))
        with self.assertRaises(ValueError):
            select_alignment_cohort(
                tenant_id="t", user_id="u", session_id="s", mode="aligned", domains="unknown",
            )


if __name__ == "__main__":
    unittest.main()
