import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.evaluation.evaluate import (  # noqa: E402
    EvaluationError,
    evaluate,
    load_json,
    main,
    markdown_report,
    write_reports,
)


EVALUATION_DIR = REPO_ROOT / "backend" / "evaluation"


class GoldenEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_json(EVALUATION_DIR / "golden_cases.v1.json")
        cls.responses = load_json(EVALUATION_DIR / "sample_responses.v1.json")

    def response_copy(self):
        return json.loads(json.dumps(self.responses))

    def test_dataset_has_required_high_value_coverage(self):
        categories = {case["category"] for case in self.cases["cases"]}
        self.assertGreaterEqual(len(self.cases["cases"]), 20)
        self.assertTrue(
            {
                "total_scope",
                "project_scope",
                "project_progress",
                "delay",
                "sap",
                "tc",
                "capacity",
                "quality",
                "named_risk",
                "stale_data",
                "missing_data",
                "ambiguity",
                "unsupported_source",
            }.issubset(categories)
        )

    def test_dataset_is_explicitly_synthetic_and_pending_business_validation(self):
        self.assertEqual(self.cases["truth_status"], "pending_business_validation")
        self.assertNotIn("business_validated", {case["validation_status"] for case in self.cases["cases"]})
        for case in self.cases["cases"]:
            with self.subTest(case_id=case["id"]):
                self.assertFalse(case["question_source"]["business_answer_imported"])
                for fact in case["expected"]["facts"]:
                    self.assertIn("tolerance", fact)
                    self.assertIn("unit", fact)
                    self.assertTrue(all(source.startswith("synthetic:") for source in fact["source_ids"]))

    def test_sample_set_runs_every_case_and_passes(self):
        report = evaluate(self.cases, self.responses)
        self.assertTrue(report["quality_gate_passed"])
        self.assertFalse(report["production_accuracy_claim"])
        self.assertEqual(report["summary"]["case_count"], len(self.cases["cases"]))
        self.assertEqual(report["summary"]["case_pass_rate"], 1.0)
        self.assertEqual(report["summary"]["overall_score"], 1.0)
        self.assertEqual(report["summary"]["unsupported_claim_count"], 0)

    def test_numeric_tolerance_accepts_small_difference_and_rejects_large_one(self):
        responses = self.response_copy()
        response = next(item for item in responses["responses"] if item["case_id"] == "total-portfolio-progress-001")
        response["facts"][0]["value"] = 58.5
        self.assertTrue(evaluate(self.cases, responses)["quality_gate_passed"])

        response["facts"][0]["value"] = 58.51
        report = evaluate(self.cases, responses)
        self.assertFalse(report["quality_gate_passed"])
        result = next(item for item in report["case_results"] if item["case_id"] == response["case_id"])
        value_check = next(check for check in result["facts"][0]["checks"] if check["dimension"] == "value")
        self.assertFalse(value_check["passed"])
        self.assertEqual(value_check["tolerance"], 0.1)

    def test_unit_source_warning_null_and_resolution_mismatches_are_reported(self):
        mutations = (
            ("project-current-progress-001", lambda response: response["facts"][0].update(unit="fraction"), "progress.unit"),
            ("sap-delayed-pos-001", lambda response: response["facts"][0].update(source_ids=[]), "delayed_po_count.source_ids"),
            ("freshness-stale-progress-001", lambda response: response.update(warning_codes=[]), "warning_codes"),
            ("missing-capex-data-001", lambda response: response["facts"][0].update(value_type="number", value=0), "capex_utilization.value_type"),
            ("ambiguous-project-name-001", lambda response: response["resolution"].update(candidate_project_ids=[]), "resolution"),
        )
        for case_id, mutate, failed_dimension in mutations:
            with self.subTest(case_id=case_id):
                responses = self.response_copy()
                response = next(item for item in responses["responses"] if item["case_id"] == case_id)
                mutate(response)
                report = evaluate(self.cases, responses)
                result = next(item for item in report["case_results"] if item["case_id"] == case_id)
                failures = [check["dimension"] for check in result["checks"] if not check["passed"]]
                failures += [f"{fact['fact_id']}.{check['dimension']}" for fact in result["facts"] for check in fact["checks"] if not check["passed"]]
                self.assertIn(failed_dimension, failures)

    def test_unexpected_fact_is_an_unsupported_claim(self):
        responses = self.response_copy()
        responses["responses"][0]["facts"].append(
            {"id": "invented_budget", "value_type": "number", "value": 99, "unit": "INR_million", "source_ids": []}
        )
        report = evaluate(self.cases, responses)
        self.assertFalse(report["quality_gate_passed"])
        self.assertEqual(report["summary"]["unsupported_claim_count"], 1)
        self.assertEqual(report["case_results"][0]["unsupported_fact_ids"], ["invented_budget"])

    def test_missing_response_fails_completeness_gate(self):
        responses = self.response_copy()
        responses["responses"].pop()
        report = evaluate(self.cases, responses)
        self.assertFalse(report["quality_gate_passed"])
        self.assertEqual(report["summary"]["missing_response_count"], 1)

    def test_report_generator_writes_json_and_markdown_without_response_payloads(self):
        report = evaluate(self.cases, self.responses)
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "report.json"
            markdown_path = Path(directory) / "report.md"
            write_reports(report, json_path, markdown_path)
            saved = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")
        self.assertEqual(saved["summary"], report["summary"])
        self.assertIn("Pending business validation", markdown)
        self.assertIn("| `total-project-count-001` |", markdown)
        self.assertNotIn("response_text", json.dumps(saved))

    def test_markdown_lists_failed_dimensions(self):
        responses = self.response_copy()
        responses["responses"][0]["facts"][0]["unit"] = "sites"
        markdown = markdown_report(evaluate(self.cases, responses))
        self.assertIn("active_project_count.unit", markdown)

    def test_rejects_old_schema_and_mismatched_dataset(self):
        cases = json.loads(json.dumps(self.cases))
        cases["schema_version"] = "1.0"
        with self.assertRaisesRegex(EvaluationError, "schema_version"):
            evaluate(cases, self.responses)
        responses = self.response_copy()
        responses["dataset_version"] = "other"
        with self.assertRaisesRegex(EvaluationError, "dataset_version"):
            evaluate(self.cases, responses)

    def test_cli_writes_both_reports_and_returns_success(self):
        with tempfile.TemporaryDirectory() as directory:
            json_path = Path(directory) / "run.json"
            markdown_path = Path(directory) / "run.md"
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = main(["--json-report", str(json_path), "--markdown-report", str(markdown_path)])
            self.assertEqual(result, 0)
            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertIn('"quality_gate_passed": true', stdout.getvalue())
            self.assertIn("Synthetic expected facts", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
