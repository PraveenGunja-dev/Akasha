import json
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.evaluation.evaluate import EvaluationError, evaluate, human_summary, load_json, main  # noqa: E402


EVALUATION_DIR = REPO_ROOT / "backend" / "evaluation"


class EvaluationFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_json(EVALUATION_DIR / "cases.v1.json")
        cls.responses = load_json(EVALUATION_DIR / "responses.v1.json")

    def test_seed_baseline_passes_and_separates_validation_cohorts(self):
        summary = evaluate(self.cases, self.responses)

        self.assertTrue(summary["quality_gate_passed"])
        self.assertFalse(summary["production_accuracy_claim"])
        self.assertEqual(summary["overall_results"]["score"], 1.0)
        self.assertEqual(summary["validated_results"]["case_count"], 0)
        self.assertIsNone(summary["validated_results"]["score"])
        self.assertEqual(summary["provisional_results"]["case_count"], 3)
        self.assertEqual(summary["provisional_results"]["score"], 1.0)
        self.assertEqual(summary["case_status_counts"], {"pending_validation": 1, "provisional": 2})
        self.assertEqual(summary["response_status_counts"], {"generated": 2, "pending_validation": 1})

    def test_seed_questions_are_workbook_derived_but_answers_are_not_imported(self):
        for case in self.cases["cases"]:
            with self.subTest(case_id=case["id"]):
                self.assertEqual(case["source"]["type"], "workbook_question")
                self.assertEqual(case["source"]["path"], "Qns_AKASHA.xlsx")
                self.assertFalse(case["source"]["business_answer_imported"])
                self.assertNotEqual(case["validation_status"], "validated")

    def test_missing_fact_and_evidence_fail_configured_gates(self):
        responses = json.loads(json.dumps(self.responses))
        responses["responses"][0]["response"] = "No deterministic expected facts are present."
        responses["responses"][0]["evidence_ids"] = []

        summary = evaluate(self.cases, responses)

        self.assertFalse(summary["quality_gate_passed"])
        failed_case = summary["case_results"][0]
        self.assertEqual(failed_case["score"], 0.0)
        grounded = next(item for item in failed_case["items"] if item["kind"] == "grounded_claim")
        self.assertFalse(grounded["text_passed"])
        self.assertFalse(grounded["evidence_passed"])

    def test_missing_response_fails_completeness_gate(self):
        responses = json.loads(json.dumps(self.responses))
        responses["responses"].pop()

        summary = evaluate(self.cases, responses)

        completeness_gate = next(
            gate for gate in summary["quality_gates"] if gate["gate"] == "require_response_for_every_case"
        )
        self.assertFalse(completeness_gate["passed"])
        self.assertEqual(summary["response_status_counts"]["missing"], 1)

    def test_machine_summary_omits_response_payloads(self):
        summary = evaluate(self.cases, self.responses)
        serialized = json.dumps(summary)

        for response in self.responses["responses"]:
            self.assertNotIn(response["response"], serialized)

    def test_human_summary_labels_scaffold_and_empty_validated_cohort(self):
        report = human_summary(evaluate(self.cases, self.responses))

        self.assertIn("NOT A PRODUCTION ACCURACY MEASUREMENT", report)
        self.assertIn("Validated: no cases", report)
        self.assertIn("Quality gates: PASS", report)

    def test_rejects_mismatched_dataset_versions(self):
        responses = json.loads(json.dumps(self.responses))
        responses["dataset_version"] = "different-version"

        with self.assertRaisesRegex(EvaluationError, "dataset_version"):
            evaluate(self.cases, responses)

    def test_rejects_unknown_case_response(self):
        responses = json.loads(json.dumps(self.responses))
        responses["responses"][0]["case_id"] = "unknown-case"

        with self.assertRaisesRegex(EvaluationError, "unknown case"):
            evaluate(self.cases, responses)

    def test_rejects_empty_or_missing_quality_gates(self):
        for replacement in ({}, None):
            with self.subTest(quality_gates=replacement):
                cases = json.loads(json.dumps(self.cases))
                if replacement is None:
                    cases.pop("quality_gates")
                else:
                    cases["quality_gates"] = replacement

                with self.assertRaisesRegex(EvaluationError, "non-empty"):
                    evaluate(cases, self.responses)

    def test_rejects_unknown_quality_gate(self):
        cases = json.loads(json.dumps(self.cases))
        cases["quality_gates"] = {"minimum_overall_socre": 0.8}

        with self.assertRaisesRegex(EvaluationError, "Unknown quality gate.*minimum_overall_socre"):
            evaluate(cases, self.responses)

    def test_rejects_completeness_gate_without_score_gate(self):
        cases = json.loads(json.dumps(self.cases))
        cases["quality_gates"] = {"require_response_for_every_case": True}

        with self.assertRaisesRegex(EvaluationError, "at least one minimum score gate"):
            evaluate(cases, self.responses)

    def test_rejects_invalid_score_gate_values(self):
        for value in (True, "0.8", -0.1, 0, 1.1, float("nan"), float("inf")):
            with self.subTest(value=value):
                cases = json.loads(json.dumps(self.cases))
                cases["quality_gates"] = {"minimum_overall_score": value}

                with self.assertRaisesRegex(EvaluationError, "greater than 0 and at most 1"):
                    evaluate(cases, self.responses)

    def test_rejects_invalid_completeness_gate_values(self):
        for value in (False, 1, "true"):
            with self.subTest(value=value):
                cases = json.loads(json.dumps(self.cases))
                cases["quality_gates"] = {
                    "minimum_overall_score": 0.8,
                    "require_response_for_every_case": value,
                }

                with self.assertRaisesRegex(EvaluationError, "must be true"):
                    evaluate(cases, self.responses)

    def test_malformed_gates_exit_nonzero_without_reporting_pass(self):
        cases = json.loads(json.dumps(self.cases))
        cases["quality_gates"] = {}
        responses = json.loads(json.dumps(self.responses))
        responses["responses"] = []
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("backend.evaluation.evaluate.load_json", side_effect=[cases, responses]):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(["--cases", "unused-cases.json", "--responses", "unused-responses.json"])

        self.assertEqual(exit_code, 2)
        self.assertIn("Evaluation input error", stderr.getvalue())
        self.assertNotIn("PASS", stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
