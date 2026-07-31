"""Deterministically compare canonical facts in a versioned golden dataset."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, NotRequired, TypedDict

try:
    from .config import (
        CASE_STATUSES,
        DEFAULT_CASES_PATH,
        DEFAULT_JSON_REPORT_PATH,
        DEFAULT_MARKDOWN_REPORT_PATH,
        DEFAULT_RESPONSES_PATH,
        FACT_TYPES,
        KNOWN_GATES,
        RESOLUTION_STATUSES,
        RESPONSE_STATUSES,
        SCHEMA_VERSION,
    )
except ImportError:  # Allows direct execution from the repository root.
    from config import (  # type: ignore[no-redef]
        CASE_STATUSES,
        DEFAULT_CASES_PATH,
        DEFAULT_JSON_REPORT_PATH,
        DEFAULT_MARKDOWN_REPORT_PATH,
        DEFAULT_RESPONSES_PATH,
        FACT_TYPES,
        KNOWN_GATES,
        RESOLUTION_STATUSES,
        RESPONSE_STATUSES,
        SCHEMA_VERSION,
    )


class EvaluationError(ValueError):
    """Raised when evaluation input does not satisfy the golden contract."""


class CheckDict(TypedDict):
    dimension: str
    passed: bool
    expected: Any
    actual: Any
    tolerance: NotRequired[float]


@dataclass(frozen=True)
class FactResult:
    fact_id: str
    passed: bool
    checks: list[CheckDict]


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    category: str
    validation_status: str
    response_status: str
    response_present: bool
    passed: bool
    passed_checks: int
    total_checks: int
    score: float
    unsupported_fact_ids: list[str]
    checks: list[CheckDict]
    facts: list[FactResult]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluationError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"Could not load {path}: {exc}") from exc
    _require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def _validate_resolution(value: Any, owner: str) -> None:
    _require(isinstance(value, dict), f"{owner} resolution must be an object")
    _require(value.get("status") in RESOLUTION_STATUSES, f"Invalid resolution status for {owner}")
    project_id = value.get("project_id")
    _require(project_id is None or isinstance(project_id, str), f"Invalid project_id for {owner}")
    candidates = value.get("candidate_project_ids", [])
    _require(
        isinstance(candidates, list) and all(isinstance(item, str) and item for item in candidates),
        f"Invalid resolution candidates for {owner}",
    )
    if value["status"] == "resolved":
        _require(bool(project_id), f"Resolved {owner} must include project_id")
    else:
        _require(project_id is None, f"Unresolved {owner} project_id must be null")


def _validate_sources(value: Any, owner: str) -> None:
    _require(
        isinstance(value, list) and all(isinstance(item, str) and item for item in value),
        f"{owner} source_ids must be a string list",
    )
    _require(len(value) == len(set(value)), f"Duplicate source_id for {owner}")


def _validate_fact(fact: Any, owner: str, *, expected: bool) -> None:
    _require(isinstance(fact, dict), f"Facts for {owner} must be objects")
    fact_id = fact.get("id")
    _require(isinstance(fact_id, str) and fact_id, f"Fact for {owner} needs an id")
    value_type = fact.get("value_type")
    _require(value_type in FACT_TYPES, f"Invalid value_type for {owner}/{fact_id}")
    value = fact.get("value")
    if value_type == "null":
        _require(value is None, f"Null fact {owner}/{fact_id} must have null value")
    elif value_type == "boolean":
        _require(isinstance(value, bool), f"Boolean fact {owner}/{fact_id} has invalid value")
    elif value_type == "integer":
        _require(isinstance(value, int) and not isinstance(value, bool), f"Integer fact {owner}/{fact_id} has invalid value")
    elif value_type == "number":
        _require(
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value),
            f"Number fact {owner}/{fact_id} has invalid value",
        )
    else:
        _require(isinstance(value, str) and value, f"Text fact {owner}/{fact_id} has invalid value")
    unit = fact.get("unit")
    _require(unit is None or isinstance(unit, str), f"Invalid unit for {owner}/{fact_id}")
    _validate_sources(fact.get("source_ids"), f"{owner}/{fact_id}")
    if expected:
        tolerance = fact.get("tolerance")
        _require(
            isinstance(tolerance, (int, float))
            and not isinstance(tolerance, bool)
            and math.isfinite(tolerance)
            and tolerance >= 0,
            f"Invalid tolerance for {owner}/{fact_id}",
        )


def _validate_inputs(cases_doc: dict[str, Any], responses_doc: dict[str, Any]) -> None:
    _require(cases_doc.get("schema_version") == SCHEMA_VERSION, "Unsupported cases schema_version")
    _require(responses_doc.get("schema_version") == SCHEMA_VERSION, "Unsupported responses schema_version")
    dataset_version = cases_doc.get("dataset_version")
    _require(isinstance(dataset_version, str) and dataset_version, "Missing cases dataset_version")
    _require(responses_doc.get("dataset_version") == dataset_version, "Cases and responses dataset_version values must match")
    _require(cases_doc.get("truth_status") == "pending_business_validation", "Dataset truth_status must remain pending_business_validation")

    gates = cases_doc.get("quality_gates")
    _require(isinstance(gates, dict) and gates, "quality_gates must be a non-empty object")
    _require(not (set(gates) - KNOWN_GATES), "Unknown quality gate(s): " + ", ".join(sorted(set(gates) - KNOWN_GATES)))
    for name in ("minimum_overall_score", "minimum_case_pass_rate"):
        if name in gates:
            value = gates[name]
            _require(isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value <= 1, f"{name} must be greater than 0 and at most 1")
    if "maximum_unsupported_claims" in gates:
        value = gates["maximum_unsupported_claims"]
        _require(isinstance(value, int) and not isinstance(value, bool) and value >= 0, "maximum_unsupported_claims must be a non-negative integer")
    if "require_response_for_every_case" in gates:
        _require(gates["require_response_for_every_case"] is True, "require_response_for_every_case must be true")

    cases = cases_doc.get("cases")
    responses = responses_doc.get("responses")
    _require(isinstance(cases, list) and len(cases) >= 20, "Golden dataset must contain at least 20 cases")
    _require(isinstance(responses, list), "Responses must be a list")
    case_ids: set[str] = set()
    for case in cases:
        _require(isinstance(case, dict), "Each case must be an object")
        case_id = case.get("id")
        _require(isinstance(case_id, str) and case_id and case_id not in case_ids, f"Invalid or duplicate case id: {case_id}")
        case_ids.add(case_id)
        _require(case.get("validation_status") in CASE_STATUSES, f"Invalid validation status for {case_id}")
        _require(isinstance(case.get("category"), str) and case["category"], f"Missing category for {case_id}")
        _require(isinstance(case.get("question"), str) and case["question"], f"Missing question for {case_id}")
        source = case.get("question_source")
        _require(isinstance(source, dict) and source.get("business_answer_imported") is False, f"Invalid question source for {case_id}")
        expected = case.get("expected")
        _require(isinstance(expected, dict), f"Missing expected result for {case_id}")
        _validate_resolution(expected.get("resolution"), f"case {case_id}")
        _validate_sources(expected.get("source_ids"), f"case {case_id}")
        warnings = expected.get("warning_codes")
        _require(isinstance(warnings, list) and all(isinstance(item, str) and item for item in warnings), f"Invalid warning_codes for {case_id}")
        facts = expected.get("facts")
        _require(isinstance(facts, list) and facts, f"Case {case_id} must have expected facts")
        fact_ids: set[str] = set()
        for fact in facts:
            _validate_fact(fact, f"case {case_id}", expected=True)
            _require(fact["id"] not in fact_ids, f"Duplicate fact id for {case_id}: {fact['id']}")
            fact_ids.add(fact["id"])

    response_ids: set[str] = set()
    for response in responses:
        _require(isinstance(response, dict), "Each response must be an object")
        case_id = response.get("case_id")
        _require(case_id in case_ids and case_id not in response_ids, f"Unknown or duplicate response case_id: {case_id}")
        response_ids.add(case_id)
        _require(response.get("validation_status") in RESPONSE_STATUSES, f"Invalid response status for {case_id}")
        _validate_resolution(response.get("resolution"), f"response {case_id}")
        _validate_sources(response.get("source_ids"), f"response {case_id}")
        warnings = response.get("warning_codes")
        _require(isinstance(warnings, list) and all(isinstance(item, str) and item for item in warnings), f"Invalid response warning_codes for {case_id}")
        facts = response.get("facts")
        _require(isinstance(facts, list), f"Response facts for {case_id} must be a list")
        fact_ids: set[str] = set()
        for fact in facts:
            _validate_fact(fact, f"response {case_id}", expected=False)
            _require(fact["id"] not in fact_ids, f"Duplicate response fact id for {case_id}: {fact['id']}")
            fact_ids.add(fact["id"])


def _check(dimension: str, expected: Any, actual: Any, passed: bool | None = None) -> CheckDict:
    return {"dimension": dimension, "passed": expected == actual if passed is None else passed, "expected": expected, "actual": actual}


def _fact_result(expected: dict[str, Any], actual: dict[str, Any] | None) -> FactResult:
    if actual is None:
        checks = [_check(name, expected.get(name), None, False) for name in ("value_type", "value", "unit", "source_ids")]
        return FactResult(expected["id"], False, checks)
    type_check = _check("value_type", expected["value_type"], actual["value_type"])
    if expected["value_type"] in {"number", "integer"} and actual["value_type"] in {"number", "integer"}:
        delta = abs(float(expected["value"]) - float(actual["value"]))
        tolerance = expected["tolerance"]
        within_tolerance = delta <= tolerance or math.isclose(delta, tolerance, rel_tol=1e-12, abs_tol=1e-12)
        value_check = _check("value", expected["value"], actual["value"], within_tolerance)
        value_check["tolerance"] = tolerance
    else:
        value_check = _check("value", expected["value"], actual["value"])
    checks = [
        type_check,
        value_check,
        _check("unit", expected.get("unit"), actual.get("unit")),
        _check("source_ids", sorted(expected["source_ids"]), sorted(actual["source_ids"])),
    ]
    return FactResult(expected["id"], all(item["passed"] for item in checks), checks)


def evaluate(cases_doc: dict[str, Any], responses_doc: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic, response-payload-free structured evaluation report."""
    _validate_inputs(cases_doc, responses_doc)
    responses = {item["case_id"]: item for item in responses_doc["responses"]}
    case_results: list[CaseResult] = []
    for case in cases_doc["cases"]:
        expected = case["expected"]
        response = responses.get(case["id"])
        actual_facts = {item["id"]: item for item in response["facts"]} if response else {}
        expected_fact_ids = {item["id"] for item in expected["facts"]}
        unsupported = sorted(set(actual_facts) - expected_fact_ids)
        top_checks = [
            _check("resolution", expected["resolution"], response.get("resolution") if response else None),
            _check("source_ids", sorted(expected["source_ids"]), sorted(response["source_ids"]) if response else None),
            _check("warning_codes", sorted(expected["warning_codes"]), sorted(response["warning_codes"]) if response else None),
            _check("unsupported_fact_ids", [], unsupported),
        ]
        facts = [_fact_result(item, actual_facts.get(item["id"])) for item in expected["facts"]]
        all_checks = top_checks + [check for fact in facts for check in fact.checks]
        passed_checks = sum(item["passed"] for item in all_checks)
        case_results.append(
            CaseResult(
                case_id=case["id"],
                category=case["category"],
                validation_status=case["validation_status"],
                response_status=response["validation_status"] if response else "missing",
                response_present=response is not None,
                passed=passed_checks == len(all_checks),
                passed_checks=passed_checks,
                total_checks=len(all_checks),
                score=passed_checks / len(all_checks),
                unsupported_fact_ids=unsupported,
                checks=top_checks,
                facts=facts,
            )
        )

    total_checks = sum(item.total_checks for item in case_results)
    passed_checks = sum(item.passed_checks for item in case_results)
    passed_cases = sum(item.passed for item in case_results)
    unsupported_claims = sum(len(item.unsupported_fact_ids) for item in case_results)
    summary = {
        "case_count": len(case_results),
        "passed_cases": passed_cases,
        "failed_cases": len(case_results) - passed_cases,
        "case_pass_rate": passed_cases / len(case_results),
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "overall_score": passed_checks / total_checks,
        "unsupported_claim_count": unsupported_claims,
        "missing_response_count": sum(not item.response_present for item in case_results),
    }
    gates = cases_doc["quality_gates"]
    gate_results = []
    gate_values = {
        "minimum_overall_score": summary["overall_score"],
        "minimum_case_pass_rate": summary["case_pass_rate"],
        "maximum_unsupported_claims": unsupported_claims,
        "require_response_for_every_case": summary["missing_response_count"] == 0,
    }
    for name, threshold in gates.items():
        actual = gate_values[name]
        passed = actual >= threshold if name.startswith("minimum_") else actual <= threshold
        if name == "require_response_for_every_case":
            passed = actual is True
        gate_results.append({"gate": name, "threshold": threshold, "actual": actual, "passed": passed})

    return {
        "report_type": "phase10_structured_golden_evaluation",
        "production_accuracy_claim": False,
        "business_validation": cases_doc["truth_status"],
        "schema_version": SCHEMA_VERSION,
        "dataset_version": cases_doc["dataset_version"],
        "summary": summary,
        "category_counts": dict(sorted(Counter(case["category"] for case in cases_doc["cases"]).items())),
        "case_status_counts": dict(sorted(Counter(case["validation_status"] for case in cases_doc["cases"]).items())),
        "quality_gates": gate_results,
        "quality_gate_passed": all(item["passed"] for item in gate_results),
        "case_results": [asdict(item) for item in case_results],
    }


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Phase 10 Golden Evaluation Report",
        "",
        "> Synthetic expected facts. Pending business validation. This is not a production accuracy claim.",
        "",
        f"- Dataset: `{report['dataset_version']}` (schema `{report['schema_version']}`)",
        f"- Result: **{'PASS' if report['quality_gate_passed'] else 'FAIL'}**",
        f"- Cases: {summary['passed_cases']}/{summary['case_count']} passed ({summary['case_pass_rate']:.1%})",
        f"- Structured checks: {summary['passed_checks']}/{summary['total_checks']} ({summary['overall_score']:.1%})",
        f"- Unsupported claims: {summary['unsupported_claim_count']}",
        f"- Missing responses: {summary['missing_response_count']}",
        "",
        "## Quality Gates",
        "",
        "| Gate | Actual | Threshold | Result |",
        "|---|---:|---:|---|",
    ]
    for gate in report["quality_gates"]:
        lines.append(f"| `{gate['gate']}` | {gate['actual']} | {gate['threshold']} | {'PASS' if gate['passed'] else 'FAIL'} |")
    lines.extend(["", "## Cases", "", "| Case | Category | Checks | Score | Result |", "|---|---|---:|---:|---|"])
    for case in report["case_results"]:
        lines.append(f"| `{case['case_id']}` | {case['category']} | {case['passed_checks']}/{case['total_checks']} | {case['score']:.1%} | {'PASS' if case['passed'] else 'FAIL'} |")
        if not case["passed"]:
            failures = [check["dimension"] for check in case["checks"] if not check["passed"]]
            failures.extend(f"{fact['fact_id']}.{check['dimension']}" for fact in case["facts"] for check in fact["checks"] if not check["passed"])
            lines.append(f"|  | Failed dimensions |  |  | {', '.join(failures)} |")
    return "\n".join(lines) + "\n"


def write_reports(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--responses", type=Path, default=DEFAULT_RESPONSES_PATH)
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT_PATH)
    parser.add_argument("--markdown-report", type=Path, default=DEFAULT_MARKDOWN_REPORT_PATH)
    args = parser.parse_args(argv)
    try:
        report = evaluate(load_json(args.cases), load_json(args.responses))
        write_reports(report, args.json_report, args.markdown_report)
    except EvaluationError as exc:
        print(f"Evaluation input error: {exc}", file=sys.stderr)
        return 2
    print(markdown_report(report), file=sys.stderr)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["quality_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
