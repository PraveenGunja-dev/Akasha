"""Run deterministic golden checks for chatbot governance behavior."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import models
from engine.agent import execute_tool, parse_tool_result
from engine.contracts import ChatRequestContract
from engine.contracts import UserScope
from engine.intent import ChatIntent, classify_intent_local
from engine.orchestrator import ChatOrchestrator
from engine.project_resolver import resolve_project
from engine.verifier import verify_numeric_claims


DEFAULT_CASES_PATH = Path(__file__).with_name("golden_cases.json")


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_cases(cases: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    cases = cases or load_cases()
    engine = create_engine("sqlite:///:memory:")
    models.Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        _seed_golden_data(db)
        results = [_run_case(db, case) for case in cases]

    passed = sum(1 for result in results if result["passed"])
    failed = len(results) - passed
    return {
        "total": len(results),
        "passed": passed,
        "failed": failed,
        "results": results,
    }


def _seed_golden_data(db: Session) -> None:
    db.add_all([
        models.ProjectMapping(
            project_id="FY25-BAIYA",
            project="Baiya Solar",
            project_name_from_p6="Baiya Solar Project",
        ),
        models.ProjectMapping(
            project_id="FY25-KHAVDA-1",
            project="Khavda Solar Block 1",
            project_name_from_p6="Khavda Block 1",
        ),
        models.ProjectMapping(
            project_id="FY25-KHAVDA-2",
            project="Khavda Solar Block 2",
            project_name_from_p6="Khavda Block 2",
        ),
    ])
    db.commit()


def _run_case(db: Session, case: dict[str, Any]) -> dict[str, Any]:
    category = case["category"]
    if category == "project_resolution":
        return _run_project_resolution_case(db, case)
    if category == "fast_authorization":
        return _run_fast_authorization_case(case)
    if category == "tool_authorization":
        return _run_tool_authorization_case(db, case)
    if category == "tool_contract":
        return _run_tool_contract_case(db, case)
    if category == "intent_classification":
        return _run_intent_classification_case(case)
    if category == "numeric_verification":
        return _run_numeric_verification_case(case)
    if category == "chat_request_contract":
        return _run_chat_request_contract_case(case)
    return _result(case, False, f"Unknown category: {category}")


def _run_project_resolution_case(db: Session, case: dict[str, Any]) -> dict[str, Any]:
    resolution = resolve_project(db, case["question"])
    failures = []
    if resolution.status != case["expected_status"]:
        failures.append(f"status={resolution.status}")
    expected_project_ids = case.get("expected_project_ids")
    if expected_project_ids is not None and resolution.project_ids != expected_project_ids:
        failures.append(f"project_ids={resolution.project_ids}")
    expected_min_candidates = case.get("expected_min_candidates")
    if expected_min_candidates is not None and len(resolution.candidates) < expected_min_candidates:
        failures.append(f"candidate_count={len(resolution.candidates)}")
    return _result(case, not failures, "; ".join(failures))


def _run_fast_authorization_case(case: dict[str, Any]) -> dict[str, Any]:
    intent_payload = case["intent"]
    intent = ChatIntent(
        projects=intent_payload.get("projects", []),
        intent_type=intent_payload.get("intent_type", "factual"),
        domains=intent_payload.get("domains", []),
        is_portfolio=intent_payload.get("is_portfolio", False),
    )
    response = ChatOrchestrator()._authorization_failure(
        intent,
        _scope_from_case(case),
        latency_ms=0,
    )
    failures = []
    if response is None:
        failures.append("request was allowed")
    elif response.status != case["expected_status"]:
        failures.append(f"status={response.status}")
    elif case.get("expected_warning") not in response.warnings:
        failures.append(f"warnings={response.warnings}")
    return _result(case, not failures, "; ".join(failures))


def _run_tool_authorization_case(db: Session, case: dict[str, Any]) -> dict[str, Any]:
    envelope = parse_tool_result(execute_tool(
        db,
        case["tool_name"],
        case.get("arguments", {}),
        user_scope=_scope_from_case(case),
    ))
    expected_status = case["expected_tool_status"]
    failures = []
    if envelope.get("status") != expected_status:
        failures.append(f"tool_status={envelope.get('status')}")
    if expected_status == "unauthorized" and envelope.get("data") is not None:
        failures.append("unauthorized envelope included data")
    return _result(case, not failures, "; ".join(failures))


def _run_tool_contract_case(db: Session, case: dict[str, Any]) -> dict[str, Any]:
    envelope = parse_tool_result(execute_tool(
        db,
        case["tool_name"],
        case.get("arguments", {}),
        user_scope=_scope_from_case(case),
    ))
    failures = []
    if envelope.get("status") != case["expected_tool_status"]:
        failures.append(f"tool_status={envelope.get('status')}")
    expected_error_contains = case.get("expected_error_contains")
    if expected_error_contains and expected_error_contains not in (envelope.get("error") or ""):
        failures.append(f"error={envelope.get('error')}")
    expected_warning_contains = case.get("expected_warning_contains")
    warnings = " ".join(envelope.get("warnings") or [])
    if expected_warning_contains and expected_warning_contains not in warnings:
        failures.append(f"warnings={envelope.get('warnings')}")
    if envelope.get("data") is not None:
        failures.append("error envelope included data")
    return _result(case, not failures, "; ".join(failures))


def _run_intent_classification_case(case: dict[str, Any]) -> dict[str, Any]:
    intent = classify_intent_local(case["question"])
    failures = []
    if intent.intent_type != case["expected_intent"]:
        failures.append(f"intent={intent.intent_type}")
    expected_portfolio = case.get("expected_is_portfolio")
    if expected_portfolio is not None and intent.is_portfolio != expected_portfolio:
        failures.append(f"is_portfolio={intent.is_portfolio}")
    for domain in case.get("expected_domains", []):
        if domain not in intent.domains:
            failures.append(f"missing_domain={domain}")
    return _result(case, not failures, "; ".join(failures))


def _run_numeric_verification_case(case: dict[str, Any]) -> dict[str, Any]:
    warnings = verify_numeric_claims(case["answer"], case.get("context", {}))
    failures = []
    expected_warning = case.get("expected_warning")
    if expected_warning and not any(expected_warning in warning for warning in warnings):
        failures.append(f"warnings={warnings}")
    if expected_warning is None and warnings:
        failures.append(f"warnings={warnings}")
    return _result(case, not failures, "; ".join(failures))


def _run_chat_request_contract_case(case: dict[str, Any]) -> dict[str, Any]:
    failures = []
    try:
        request = ChatRequestContract(**case["payload"])
    except Exception as exc:
        if case.get("expected_valid", True):
            failures.append(f"validation_error={exc}")
        return _result(case, not failures, "; ".join(failures))

    if not case.get("expected_valid", True):
        failures.append("payload unexpectedly valid")
    expected_project_id = case.get("expected_project_id")
    if expected_project_id is not None and request.project_id != expected_project_id:
        failures.append(f"project_id={request.project_id}")
    expected_session_id = case.get("expected_session_id")
    if expected_session_id is not None and request.session_id != expected_session_id:
        failures.append(f"session_id={request.session_id}")
    return _result(case, not failures, "; ".join(failures))


def _scope_from_case(case: dict[str, Any]) -> UserScope:
    return UserScope(**case["scope"], is_authenticated=True)


def _result(case: dict[str, Any], passed: bool, detail: str = "") -> dict[str, Any]:
    return {
        "id": case["id"],
        "category": case["category"],
        "severity": case.get("severity", "medium"),
        "passed": passed,
        "detail": detail,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Akasha chatbot golden evaluation cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--json", action="store_true", help="Print full JSON results.")
    args = parser.parse_args()

    report = run_cases(load_cases(args.cases))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Golden evaluation: {report['passed']}/{report['total']} passed")
        for result in report["results"]:
            status = "PASS" if result["passed"] else "FAIL"
            detail = f" - {result['detail']}" if result["detail"] else ""
            print(f"{status} {result['id']}{detail}")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
