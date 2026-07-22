"""Deterministic verification helpers for chatbot answers."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])-?\d[\d,]*(?:\.\d+)?%?")


def verify_numeric_claims(answer: str, context: Any) -> list[str]:
    """Warn when an answer contains material numbers absent from context.

    This is intentionally lightweight. It is a guardrail for obvious invented
    numeric claims, not a complete claim-level verifier.
    """
    answer_numbers = _extract_material_numbers(answer)
    if not answer_numbers:
        return []

    context_numbers = _extract_context_numbers(context)
    missing = sorted(answer_numbers - context_numbers)
    if not missing:
        return []

    shown = ", ".join(missing[:5])
    suffix = "..." if len(missing) > 5 else ""
    return [f"unverified_numeric_claims: {shown}{suffix}"]


def _extract_material_numbers(text: str) -> set[str]:
    numbers = set()
    for match in _NUMBER_RE.findall(text or ""):
        normalized = _normalize_number(match)
        if normalized and _is_material_number(normalized):
            numbers.add(normalized)
    return numbers


def _extract_context_numbers(value: Any) -> set[str]:
    numbers: set[str] = set()
    _collect_context_numbers(value, numbers)
    return numbers


def _collect_context_numbers(value: Any, numbers: set[str]) -> None:
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float, Decimal)):
        normalized = _normalize_number(str(value))
        if normalized:
            numbers.add(normalized)
        return
    if isinstance(value, str):
        for match in _NUMBER_RE.findall(value):
            normalized = _normalize_number(match)
            if normalized:
                numbers.add(normalized)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_context_numbers(item, numbers)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            _collect_context_numbers(item, numbers)


def _normalize_number(raw: str) -> str | None:
    cleaned = raw.strip().replace(",", "").replace("%", "")
    if not cleaned:
        return None
    try:
        number = Decimal(cleaned)
    except InvalidOperation:
        return None
    if number == number.to_integral_value():
        return str(number.quantize(Decimal("1")))
    return format(number.normalize(), "f")


def _is_material_number(normalized: str) -> bool:
    try:
        number = abs(Decimal(normalized))
    except InvalidOperation:
        return False
    # Avoid warning on markdown numbering and tiny list counts.
    return number > 10 or number != number.to_integral_value()
