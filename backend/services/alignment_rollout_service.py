"""Server-owned deterministic cohort selection for the aligned data adapters."""

from dataclasses import dataclass
import hashlib
import os


VALID_MODES = {"legacy", "shadow", "canary", "aligned"}
ALL_DOMAINS = frozenset({"schedule", "sap", "tc", "capacity", "quality", "risk"})


@dataclass(frozen=True)
class AlignmentDecision:
    mode: str
    cohort: str
    enabled_domains: frozenset[str]

    def uses_aligned_domain(self, domain: str) -> bool:
        return self.cohort == "aligned" and domain in self.enabled_domains


def select_alignment_cohort(
    *,
    tenant_id: str,
    user_id: str,
    session_id: str,
    mode: str | None = None,
    rollout_percent: int | None = None,
    domains: str | None = None,
) -> AlignmentDecision:
    configured_mode = (mode or os.getenv("AKASHA_ALIGNMENT_MODE", "aligned")).strip().lower()
    if configured_mode not in VALID_MODES:
        raise ValueError("AKASHA_ALIGNMENT_MODE must be legacy, shadow, canary, or aligned.")
    percent = rollout_percent if rollout_percent is not None else int(
        os.getenv("AKASHA_ALIGNMENT_ROLLOUT_PERCENT", "0")
    )
    if not 0 <= percent <= 100:
        raise ValueError("AKASHA_ALIGNMENT_ROLLOUT_PERCENT must be between 0 and 100.")
    enabled_domains = _parse_domains(domains or os.getenv("AKASHA_ALIGNMENT_DOMAINS", ",".join(sorted(ALL_DOMAINS))))
    cohort = _cohort(configured_mode, percent, tenant_id, user_id, session_id)
    return AlignmentDecision(configured_mode, cohort, enabled_domains)


def _parse_domains(value: str) -> frozenset[str]:
    domains = frozenset(item.strip().lower() for item in value.split(",") if item.strip())
    unknown = domains - ALL_DOMAINS
    if unknown:
        raise ValueError("Unknown alignment domain(s): " + ", ".join(sorted(unknown)))
    return domains


def _cohort(mode: str, percent: int, tenant_id: str, user_id: str, session_id: str) -> str:
    if mode in {"legacy", "shadow"}:
        return mode
    if mode == "aligned":
        return "aligned"
    identity = f"{tenant_id}:{user_id}:{session_id}".encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(identity).digest()[:8], "big") % 100
    return "aligned" if bucket < percent else "legacy"
