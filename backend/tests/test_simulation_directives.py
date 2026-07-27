import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from engine.simulation_directives import (  # noqa: E402
    DirectiveValidationError,
    SIMULATION_DIRECTIVE_CODES,
    build_simulation_directives,
)


EXPECTED_TASKS = {
    "P6_SCHEDULE_REVIEW": {
        "system": "P6",
        "action": "Review schedule recovery options",
        "description": (
            "A project scheduler should assess affected activities, dependencies, and approvals "
            "before requesting any schedule change."
        ),
        "status": "For Review",
    },
    "CREW_PLAN_REVIEW": {
        "system": "Operational Review",
        "action": "Review the proposed crew plan",
        "description": (
            "The project team should assess crew availability, site constraints, safety requirements, "
            "and approvals before changing the field plan."
        ),
        "status": "For Review",
    },
    "PROCUREMENT_REVIEW": {
        "system": "SAP",
        "action": "Review procurement recovery options",
        "description": (
            "A procurement reviewer should assess material availability, supplier commitments, "
            "commercial constraints, and approvals before requesting any procurement change."
        ),
        "status": "For Review",
    },
    "TC_RECOVERY_REVIEW": {
        "system": "Operational Review",
        "action": "Review transmission recovery options",
        "description": (
            "The transmission team should assess at-risk work, dependencies, contractor capacity, "
            "and required approvals before changing the recovery plan."
        ),
        "status": "For Review",
    },
    "PMAG_ACTION_REVIEW": {
        "system": "PMAG",
        "action": "Review the proposed PMAG action",
        "description": (
            "An authorized reviewer should assess the proposed project action and required approvals "
            "before requesting any PMAG change."
        ),
        "status": "For Review",
    },
}


class ClosedVocabularyTests(unittest.TestCase):
    def test_every_accepted_code_maps_to_exact_backend_owned_text(self):
        self.assertEqual(tuple(EXPECTED_TASKS), SIMULATION_DIRECTIVE_CODES)

        result = build_simulation_directives(
            {"directive_codes": list(SIMULATION_DIRECTIVE_CODES)}
        )

        self.assertEqual(result, {"tasks": list(EXPECTED_TASKS.values())})
        self.assertTrue(all(set(task) == {"system", "action", "description", "status"} for task in result["tasks"]))
        self.assertEqual({task["status"] for task in result["tasks"]}, {"For Review"})

    def test_returns_fresh_template_copies(self):
        first = build_simulation_directives({"directive_codes": ["P6_SCHEDULE_REVIEW"]})
        first["tasks"][0]["action"] = "mutated"

        second = build_simulation_directives({"directive_codes": ["P6_SCHEDULE_REVIEW"]})

        self.assertEqual(second["tasks"][0], EXPECTED_TASKS["P6_SCHEDULE_REVIEW"])

    def test_preserves_selected_code_order(self):
        codes = ["PMAG_ACTION_REVIEW", "P6_SCHEDULE_REVIEW"]
        result = build_simulation_directives({"directive_codes": codes})
        self.assertEqual(
            result["tasks"],
            [EXPECTED_TASKS["PMAG_ACTION_REVIEW"], EXPECTED_TASKS["P6_SCHEDULE_REVIEW"]],
        )


class FailClosedTests(unittest.TestCase):
    def assert_rejected_without_echo(self, payload, unsafe_text=None):
        with self.assertRaises(DirectiveValidationError) as context:
            build_simulation_directives(payload)
        if unsafe_text:
            self.assertNotIn(unsafe_text, str(context.exception))

    def test_rejects_arbitrary_prose_fields_and_old_task_shape(self):
        unsafe_text = "SAP update completed through a delegated connector"
        payloads = [
            {
                "tasks": [
                    {
                        "system": "SAP",
                        "action": unsafe_text,
                        "description": "For review",
                        "status": "For Review",
                    }
                ]
            },
            {"directive_codes": ["P6_SCHEDULE_REVIEW"], "action": unsafe_text},
            {"directive_codes": [{"code": "P6_SCHEDULE_REVIEW", "description": unsafe_text}]},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assert_rejected_without_echo(payload, unsafe_text)

    def test_rejects_unknown_duplicate_empty_and_excess_codes(self):
        payloads = [
            {"directive_codes": ["UNKNOWN_REVIEW"]},
            {"directive_codes": ["p6_schedule_review"]},
            {"directive_codes": [" P6_SCHEDULE_REVIEW "]},
            {"directive_codes": ["P6_SCHEDULE_REVIEW", "P6_SCHEDULE_REVIEW"]},
            {"directive_codes": []},
            {"directive_codes": ["P6_SCHEDULE_REVIEW"] * 6},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assert_rejected_without_echo(payload)

    def test_p0g_prose_bypasses_cannot_reach_output(self):
        bypasses = [
            "The purchase order was pushed to SAP successfully.",
            "The schedule has been synced in P6.",
            "AKASHA executed the PMAG action.",
            "Task completed successfully.",
            "Request successfully processed in Contractor Portal.",
            "Written to HRMS.",
            "The SAP record was updated.",
            "This will automatically update P6.",
            "The engine will send the task to PMAG.",
            "Sync completed successfully.",
            "Connector handoff finalized; downstream record state is current.",
        ]
        for bypass in bypasses:
            with self.subTest(bypass=bypass):
                self.assert_rejected_without_echo({"directive_codes": [bypass]}, bypass)

    def test_rejects_invalid_top_level_shapes_and_unknown_keys(self):
        payloads = [
            None,
            [],
            {},
            {"directive_codes": "P6_SCHEDULE_REVIEW"},
            {"directive_codes": [1]},
            {"directive_codes": ["P6_SCHEDULE_REVIEW"], "extra": True},
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                self.assert_rejected_without_echo(payload)


if __name__ == "__main__":
    unittest.main()
