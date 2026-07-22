"""Deterministic project resolution for chatbot requests."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Iterable

from sqlalchemy.orm import Session

import models
from engine.contracts import ProjectCandidate, ProjectResolution


_STOPWORDS = {
    "what", "why", "which", "when", "where", "give", "show", "tell", "current",
    "status", "project", "risk", "at", "for", "is", "the", "of", "in", "on",
    "progress", "duration", "activity", "activities", "overall", "planned",
    "actual", "baseline", "time", "period", "location", "solar", "there",
    "compare", "with", "as", "today", "yesterday",
}

_PROJECT_CONTEXT_TERMS = {
    "project", "site", "block", "plot", "phase", "location",
}

_PROJECT_METRIC_TERMS = {
    "progress", "status", "variance", "completion", "readiness", "capex",
    "cash", "material", "manpower", "machinery", "budget", "cost",
}


def normalize_project_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def resolve_project(
    db: Session,
    query: str | None,
    *,
    message: str | None = None,
    require_unique: bool = True,
    limit: int = 5,
) -> ProjectResolution:
    """Resolve a project name/id into a canonical project_id.

    The resolver returns candidates when the best match is not uniquely strong;
    callers should ask a clarification question instead of guessing.
    """
    search_text = (query or "").strip()
    if not search_text and message:
        search_text = _best_message_fragment(db, message)

    if not search_text:
        return ProjectResolution(status="not_project_specific")

    candidates = _rank_candidates(db, search_text, limit=limit)
    if not candidates:
        return ProjectResolution(
            status="not_found",
            confidence="insufficient",
            question=f"I could not match '{search_text}' to a known project. Which project should I use?",
        )

    best = candidates[0]
    next_score = candidates[1].score if len(candidates) > 1 else 0.0
    exact_identifier_match = (
        best.score >= 0.999
        and best.match_type in {"project_id", "p6_project_id"}
        and next_score < 0.999
    )
    unique = exact_identifier_match or (
        best.score >= 0.92 and (best.score - next_score) >= 0.08
    ) or (
        len(candidates) == 1 and best.score >= 0.90
    )

    if not require_unique or unique:
        return ProjectResolution(
            status="resolved",
            project_ids=[best.project_id],
            candidates=[best],
            confidence="high" if best.score >= 0.95 else "medium",
        )

    if best.score >= 0.70:
        names = ", ".join(c.project_name for c in candidates[:3])
        return ProjectResolution(
            status="ambiguous",
            candidates=candidates,
            confidence="low",
            question=f"I found multiple possible project matches: {names}. Which one should I use?",
        )

    return ProjectResolution(
        status="not_found",
        candidates=candidates,
        confidence="insufficient",
        question=f"I could not confidently match '{search_text}' to a known project. Please provide the project ID or exact name.",
    )


def resolve_projects_from_intent(
    db: Session,
    projects: Iterable[str],
    *,
    message: str,
    is_portfolio: bool,
) -> ProjectResolution:
    if is_portfolio:
        return ProjectResolution(status="not_project_specific")

    resolved: list[str] = []
    all_candidates: list[ProjectCandidate] = []
    for project in projects:
        result = resolve_project(db, project)
        all_candidates.extend(result.candidates)
        if result.status != "resolved":
            return result
        resolved.extend(result.project_ids)

    if resolved:
        return ProjectResolution(
            status="resolved",
            project_ids=list(dict.fromkeys(resolved)),
            candidates=all_candidates,
            confidence="high",
        )

    result = resolve_project(db, None, message=message)
    if result.status != "not_project_specific":
        return result

    if _message_requires_project_context(message):
        return ProjectResolution(
            status="not_found",
            confidence="insufficient",
            question="Which project should I use?",
        )

    return result


def _rank_candidates(db: Session, search_text: str, *, limit: int) -> list[ProjectCandidate]:
    needle = normalize_project_text(search_text)
    if not needle:
        return []

    scored: dict[str, ProjectCandidate] = {}
    mappings = db.query(models.ProjectMapping).all()

    for mapping in mappings:
        if not mapping.project_id:
            continue
        project_name = mapping.project_name_from_p6 or mapping.project or mapping.project_id
        names = {
            "project_id": mapping.project_id,
            "project": mapping.project,
            "p6_name": mapping.project_name_from_p6,
            "spv_name": mapping.spv_name,
        }
        for match_type, value in names.items():
            score = _score(needle, value, match_type=match_type)
            if score <= 0:
                continue
            existing = scored.get(mapping.project_id)
            if existing is None or score > existing.score:
                scored[mapping.project_id] = ProjectCandidate(
                    project_id=mapping.project_id,
                    project_name=project_name,
                    p6_name=mapping.project_name_from_p6,
                    spv_name=mapping.spv_name,
                    score=round(score, 3),
                    match_type=match_type,
                )

    mapping_by_pid = {mapping.project_id: mapping for mapping in mappings if mapping.project_id}
    p6_projects = db.query(models.P6Project).all()
    for project in p6_projects:
        if not project.project_id:
            continue
        names = {
            "p6_project_id": project.project_id,
            "p6_project_name": project.name,
        }
        for match_type, value in names.items():
            score = _score(needle, value, match_type=match_type)
            if score <= 0:
                continue

            mapping = mapping_by_pid.get(project.project_id)
            project_name = (
                mapping.project_name_from_p6 or mapping.project
            ) if mapping else None
            project_name = project_name or project.name or project.project_id
            p6_name = project.name or (mapping.project_name_from_p6 if mapping else None)
            spv_name = mapping.spv_name if mapping else None

            existing = scored.get(project.project_id)
            if existing is None or score > existing.score:
                scored[project.project_id] = ProjectCandidate(
                    project_id=project.project_id,
                    project_name=project_name,
                    p6_name=p6_name,
                    spv_name=spv_name,
                    score=round(score, 3),
                    match_type=match_type,
                )

    return sorted(scored.values(), key=lambda c: c.score, reverse=True)[:limit]


def _score(needle: str, raw_value: str | None, *, match_type: str = "") -> float:
    value = normalize_project_text(raw_value)
    if not value:
        return 0.0
    if needle == value:
        return 1.0
    if match_type in {"project_id", "p6_project_id"}:
        if value.startswith(f"{needle} ") or needle.startswith(f"{value} "):
            return 0.96
    if needle in value:
        return 0.9 if len(needle) >= 4 else 0.75
    if value in needle:
        return 0.86 if len(value) >= 4 else 0.65
    ratio = SequenceMatcher(None, needle, value).ratio()
    return ratio if ratio >= 0.68 else 0.0


def _best_message_fragment(db: Session, message: str) -> str:
    normalized = normalize_project_text(message)
    best_fragment = ""
    best_score = 0.0

    raw_words = normalized.split()
    filtered_words = [w for w in raw_words if w not in _STOPWORDS]

    # Preserve explicit project-code tokens before stopword filtering. Codes like
    # GEN-STATUS or FY25-BAIYA can contain words that are otherwise generic.
    fragments = _explicit_project_code_fragments(message) + _message_fragments(filtered_words)

    for fragment in fragments:
        candidates = _rank_candidates(db, fragment, limit=2)
        if not candidates:
            continue
        next_score = candidates[1].score if len(candidates) > 1 else 0.0
        if (
            candidates[0].score >= 0.90
            and candidates[0].score > best_score
            and (candidates[0].score - next_score) >= 0.08
        ):
            best_fragment = fragment
            best_score = candidates[0].score

    return best_fragment


def _explicit_project_code_fragments(message: str) -> list[str]:
    """Extract obvious project-code fragments from free text."""
    raw_fragments = re.findall(
        r"\b[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)+\b",
        message or "",
    )
    return list(dict.fromkeys(normalize_project_text(fragment) for fragment in raw_fragments))


def _message_requires_project_context(message: str) -> bool:
    raw = message or ""
    normalized = normalize_project_text(raw)
    words = set(normalized.split())

    if "which projects" in normalized or "all projects" in normalized or "portfolio" in normalized:
        return False

    if re.search(r"\b(x|y|z|xyz)\b", raw, flags=re.IGNORECASE):
        return True
    if "time period" in normalized or "time_period" in raw.lower():
        return True
    if "dependencies" in words and "delay" in words:
        return True
    if "baseline" in words and ({"completion", "variance", "date", "plan"} & words):
        return True

    has_context_term = bool(words & _PROJECT_CONTEXT_TERMS)
    has_metric_term = bool(words & _PROJECT_METRIC_TERMS)

    if has_context_term and has_metric_term:
        return True

    if re.search(r"\b(project|site|block|plot|phase)\s+[a-z0-9-]+\b", normalized):
        return True

    return False


def _message_fragments(words: list[str], *, max_words: int = 6) -> list[str]:
    fragments: list[str] = []
    for size in range(min(max_words, len(words)), 0, -1):
        for start in range(0, len(words) - size + 1):
            fragment_words = words[start:start + size]
            if len("".join(fragment_words)) < 4:
                continue
            fragments.append(" ".join(fragment_words))
    return fragments
