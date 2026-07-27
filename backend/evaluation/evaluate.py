"""Score versioned provisional responses without databases or model providers."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
CASE_STATUSES = {"validated", "provisional", "pending_validation"}
RESPONSE_STATUSES = {"validated", "generated", "pending_validation"}
SCORE_GATE_NAMES = {
    "minimum_overall_score",
    "minimum_validated_score",
    "minimum_provisional_score",
}
KNOWN_GATE_NAMES = SCORE_GATE_NAMES | {"require_response_for_every_case"}


class EvaluationError(ValueError):
    """Raised when evaluation input does not satisfy the scaffold contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluationError(message)


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvaluationError(f"Could not load {path}: {exc}") from exc
    _require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def _validate_inputs(cases_doc: dict[str, Any], responses_doc: dict[str, Any]) -> None:
    _require(cases_doc.get("schema_version") == SCHEMA_VERSION, "Unsupported cases schema_version")
    _require(
        responses_doc.get("schema_version") == SCHEMA_VERSION,
        "Unsupported responses schema_version",
    )
    dataset_version = cases_doc.get("dataset_version")
    _require(isinstance(dataset_version, str) and dataset_version, "Missing cases dataset_version")
    _require(
        responses_doc.get("dataset_version") == dataset_version,
        "Cases and responses dataset_version values must match",
    )

    gates = cases_doc.get("quality_gates")
    _require(isinstance(gates, dict) and gates, "quality_gates must be a non-empty object")
    unknown_gates = set(gates) - KNOWN_GATE_NAMES
    _require(not unknown_gates, f"Unknown quality gate(s): {', '.join(sorted(unknown_gates))}")
    _require(
        bool(set(gates) & SCORE_GATE_NAMES),
        "quality_gates must configure at least one minimum score gate",
    )
    for gate_name in SCORE_GATE_NAMES & set(gates):
        threshold = gates[gate_name]
        _require(
            isinstance(threshold, (int, float))
            and not isinstance(threshold, bool)
            and math.isfinite(threshold)
            and 0 < threshold <= 1,
            f"{gate_name} must be a number greater than 0 and at most 1",
        )
    if "require_response_for_every_case" in gates:
        _require(
            gates["require_response_for_every_case"] is True,
            "require_response_for_every_case must be true when configured",
        )

    cases = cases_doc.get("cases")
    responses = responses_doc.get("responses")
    _require(isinstance(cases, list) and cases, "Cases must be a non-empty list")
    _require(isinstance(responses, list), "Responses must be a list")

    case_ids: set[str] = set()
    for case in cases:
        _require(isinstance(case, dict), "Each case must be an object")
        case_id = case.get("id")
        _require(isinstance(case_id, str) and case_id, "Each case needs a non-empty id")
        _require(case_id not in case_ids, f"Duplicate case id: {case_id}")
        case_ids.add(case_id)
        _require(case.get("validation_status") in CASE_STATUSES, f"Invalid status for {case_id}")
        _require(isinstance(case.get("question"), str) and case["question"], f"Missing question for {case_id}")
        facts = case.get("expected_facts", [])
        claims = case.get("grounded_claims", [])
        _require(isinstance(facts, list) and isinstance(claims, list), f"Invalid rubric for {case_id}")
        _require(bool(facts or claims), f"Case {case_id} has no scorable rubric items")
        rubric_ids: set[str] = set()
        for item in facts + claims:
            _require(isinstance(item, dict), f"Rubric items for {case_id} must be objects")
            item_id = item.get("id")
            expected_text = item.get("expected_text")
            _require(isinstance(item_id, str) and item_id, f"Rubric item in {case_id} needs an id")
            _require(item_id not in rubric_ids, f"Duplicate rubric id in {case_id}: {item_id}")
            rubric_ids.add(item_id)
            _require(
                isinstance(expected_text, str) and expected_text,
                f"Rubric item {item_id} in {case_id} needs expected_text",
            )
        for claim in claims:
            evidence_ids = claim.get("required_evidence_ids")
            _require(
                isinstance(evidence_ids, list)
                and evidence_ids
                and all(isinstance(value, str) and value for value in evidence_ids),
                f"Grounded claim {claim['id']} in {case_id} needs evidence IDs",
            )

    response_ids: set[str] = set()
    for response in responses:
        _require(isinstance(response, dict), "Each response must be an object")
        case_id = response.get("case_id")
        _require(isinstance(case_id, str) and case_id, "Each response needs a case_id")
        _require(case_id in case_ids, f"Response references unknown case: {case_id}")
        _require(case_id not in response_ids, f"Duplicate response for case: {case_id}")
        response_ids.add(case_id)
        _require(
            response.get("validation_status") in RESPONSE_STATUSES,
            f"Invalid response status for {case_id}",
        )
        _require(isinstance(response.get("response"), str), f"Invalid response text for {case_id}")
        evidence_ids = response.get("evidence_ids", [])
        _require(
            isinstance(evidence_ids, list)
            and all(isinstance(value, str) and value for value in evidence_ids),
            f"Invalid evidence_ids for {case_id}",
        )


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(result["passed_items"] for result in results)
    total = sum(result["total_items"] for result in results)
    return {
        "case_count": len(results),
        "passed_items": passed,
        "total_items": total,
        "score": passed / total if total else None,
    }


def evaluate(cases_doc: dict[str, Any], responses_doc: dict[str, Any]) -> dict[str, Any]:
    """Return a payload-free deterministic score summary for two versioned documents."""
    _validate_inputs(cases_doc, responses_doc)
    responses = {response["case_id"]: response for response in responses_doc["responses"]}
    results: list[dict[str, Any]] = []

    for case in cases_doc["cases"]:
        response = responses.get(case["id"])
        response_text = _normalized(response["response"]) if response else ""
        evidence = set(response.get("evidence_ids", [])) if response else set()
        item_results: list[dict[str, Any]] = []

        for fact in case.get("expected_facts", []):
            passed = _normalized(fact["expected_text"]) in response_text
            item_results.append({"id": fact["id"], "kind": "fact", "passed": passed})

        for claim in case.get("grounded_claims", []):
            required_evidence = set(claim["required_evidence_ids"])
            text_passed = _normalized(claim["expected_text"]) in response_text
            evidence_passed = required_evidence.issubset(evidence)
            item_results.append(
                {
                    "id": claim["id"],
                    "kind": "grounded_claim",
                    "passed": text_passed and evidence_passed,
                    "text_passed": text_passed,
                    "evidence_passed": evidence_passed,
                }
            )

        passed_items = sum(item["passed"] for item in item_results)
        total_items = len(item_results)
        results.append(
            {
                "case_id": case["id"],
                "case_validation_status": case["validation_status"],
                "response_validation_status": response["validation_status"] if response else "missing",
                "response_present": response is not None,
                "passed_items": passed_items,
                "total_items": total_items,
                "score": passed_items / total_items,
                "items": item_results,
            }
        )

    validated_results = [result for result in results if result["case_validation_status"] == "validated"]
    provisional_results = [result for result in results if result["case_validation_status"] != "validated"]
    overall = _aggregate(results)
    validated = _aggregate(validated_results)
    provisional = _aggregate(provisional_results)
    gates = cases_doc["quality_gates"]
    gate_results: list[dict[str, Any]] = []

    for gate_name, aggregate in (
        ("minimum_overall_score", overall),
        ("minimum_validated_score", validated),
        ("minimum_provisional_score", provisional),
    ):
        if gate_name not in gates:
            continue
        threshold = gates[gate_name]
        actual = aggregate["score"]
        gate_results.append(
            {
                "gate": gate_name,
                "threshold": threshold,
                "actual": actual,
                "passed": actual is not None and actual >= threshold,
            }
        )

    if "require_response_for_every_case" in gates:
        actual = all(result["response_present"] for result in results)
        gate_results.append(
            {
                "gate": "require_response_for_every_case",
                "threshold": True,
                "actual": actual,
                "passed": actual,
            }
        )

    return {
        "summary_type": "provisional_evaluation_scaffold",
        "production_accuracy_claim": False,
        "schema_version": SCHEMA_VERSION,
        "dataset_version": cases_doc["dataset_version"],
        "overall_results": overall,
        "validated_results": validated,
        "provisional_results": provisional,
        "case_status_counts": dict(sorted(Counter(case["validation_status"] for case in cases_doc["cases"]).items())),
        "response_status_counts": dict(
            sorted(Counter(result["response_validation_status"] for result in results).items())
        ),
        "case_results": results,
        "quality_gates": gate_results,
        "quality_gate_passed": bool(gate_results) and all(gate["passed"] for gate in gate_results),
    }


def human_summary(summary: dict[str, Any]) -> str:
    def result_line(label: str, result: dict[str, Any]) -> str:
        if result["score"] is None:
            return f"{label}: no cases"
        return (
            f"{label}: {result['passed_items']}/{result['total_items']} items "
            f"({result['score']:.1%}) across {result['case_count']} case(s)"
        )

    lines = [
        "PROVISIONAL EVALUATION SCAFFOLD - NOT A PRODUCTION ACCURACY MEASUREMENT",
        f"Dataset: {summary['dataset_version']} (schema {summary['schema_version']})",
        result_line("Overall", summary["overall_results"]),
        result_line("Validated", summary["validated_results"]),
        result_line("Provisional/non-validated", summary["provisional_results"]),
        f"Case statuses: {json.dumps(summary['case_status_counts'], sort_keys=True)}",
        f"Response statuses: {json.dumps(summary['response_status_counts'], sort_keys=True)}",
        "Cases:",
    ]
    for result in summary["case_results"]:
        lines.append(
            f"  {result['case_id']}: {result['passed_items']}/{result['total_items']} "
            f"[{result['case_validation_status']}; response={result['response_validation_status']}]"
        )
    lines.append(f"Quality gates: {'PASS' if summary['quality_gate_passed'] else 'FAIL'}")
    for gate in summary["quality_gates"]:
        lines.append(
            f"  {gate['gate']}: {'PASS' if gate['passed'] else 'FAIL'} "
            f"(actual={gate['actual']!r}, threshold={gate['threshold']!r})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    base_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=base_dir / "cases.v1.json")
    parser.add_argument("--responses", type=Path, default=base_dir / "responses.v1.json")
    args = parser.parse_args(argv)
    try:
        summary = evaluate(load_json(args.cases), load_json(args.responses))
    except EvaluationError as exc:
        print(f"Evaluation input error: {exc}", file=sys.stderr)
        return 2
    print(human_summary(summary), file=sys.stderr)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["quality_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
