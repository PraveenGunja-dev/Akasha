from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

import models


MAX_REPORT_VISUALIZATIONS = 12

_DOMAIN_KEYWORDS = {
    "schedule": ("schedule", "p6", "activity", "activities", "progress", "delay", "baseline", "block"),
    "procurement": ("procurement", "sap", "purchase order", "material", "vendor", "fulfil", "fulfill"),
    "transmission": ("transmission", "grid", "line", "substation", "tc"),
    "quality": ("quality", "non-conformance", "nonconformance", "ncr", "rfi", "pulse"),
    "capacity": ("capacity", "mw", "cod", "commission"),
    "risk": ("risk", "exposure", "critical"),
}


def _normalized_json(value: object) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def visualization_hash(visualization: dict) -> str:
    return "sha256:" + hashlib.sha256(_normalized_json(visualization).encode("utf-8")).hexdigest()


def _project_ids(message: models.ChatMessage, visualization: dict) -> set[str]:
    ids = {item.strip() for item in str(message.project_ids or "").split(",") if item.strip()}
    for container in (visualization, visualization.get("spec") or {}):
        value = container.get("project_id") if isinstance(container, dict) else None
        if value:
            ids.add(str(value))
        values = container.get("project_ids") if isinstance(container, dict) else None
        if isinstance(values, list):
            ids.update(str(item) for item in values if item)
    return ids


def _searchable_text(visualization: dict) -> str:
    spec = visualization.get("spec") if isinstance(visualization.get("spec"), dict) else {}
    return " ".join(str(value or "") for value in (
        visualization.get("title"), visualization.get("subtitle"), visualization.get("summary"),
        visualization.get("chart_type"), spec.get("title"), spec.get("subtitle"), spec.get("summary"),
        spec.get("chart_type"), " ".join(spec.get("source_tables") or []),
    )).casefold()


def classify_domain(visualization: dict) -> str:
    text = _searchable_text(visualization)
    scores = {
        domain: sum(1 for keyword in keywords if keyword in text)
        for domain, keywords in _DOMAIN_KEYWORDS.items()
    }
    domain, score = max(scores.items(), key=lambda item: item[1])
    return domain if score else "appendix"


def _requested_domains(selection_text: str | None) -> set[str]:
    text = str(selection_text or "").casefold()
    text = re.split(r"\b(?:exclude|omit|without|except)\b", text, maxsplit=1)[0]
    domains = {
        domain for domain, keywords in _DOMAIN_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }
    # "progress report" is normally the report name, not a request to exclude every
    # non-schedule chart. Treat it as a filter only alongside selection language.
    if domains == {"schedule"} and not re.search(r"\b(?:only|include|chart|graph|visual)\b", text):
        return set()
    return domains


def _excluded_terms(selection_text: str | None) -> tuple[str, ...]:
    text = str(selection_text or "").casefold()
    match = re.search(r"\b(?:exclude|omit|without|except)\s+(.+)", text)
    if not match:
        return ()
    tail = re.split(r"[.;]", match.group(1), maxsplit=1)[0]
    terms = []
    for term in re.split(r",|\band\b", tail):
        cleaned = re.sub(r"\b(?:charts?|graphs?|visualizations?|from|the|report)\b", " ", term)
        cleaned = " ".join(cleaned.split())
        if cleaned:
            terms.append(cleaned)
    return tuple(terms)[:8]


def _excluded_domains(selection_text: str | None) -> set[str]:
    text = str(selection_text or "").casefold()
    match = re.search(r"\b(?:exclude|omit|without|except)\s+(.+)", text)
    if not match:
        return set()
    tail = re.split(r"[.;]", match.group(1), maxsplit=1)[0]
    return {
        domain for domain, keywords in _DOMAIN_KEYWORDS.items()
        if any(keyword in tail for keyword in keywords)
    }


def _last_requested_count(selection_text: str | None) -> int | None:
    match = re.search(r"\b(?:last|latest|most recent)\s+(\d{1,2})\s+(?:charts?|graphs?|visualizations?)\b", str(selection_text or ""), re.I)
    return min(int(match.group(1)), MAX_REPORT_VISUALIZATIONS) if match else None


@dataclass(frozen=True)
class SelectedVisualization:
    message_id: int
    index: int
    snapshot_hash: str
    visualization: dict
    domain: str
    reason: str

    def reference(self) -> dict:
        return {"m": self.message_id, "i": self.index, "h": self.snapshot_hash}

    def report_payload(self) -> dict:
        spec = self.visualization.get("spec") if isinstance(self.visualization.get("spec"), dict) else {}
        return {
            **self.visualization,
            "title": self.visualization.get("title") or spec.get("title") or "Conversation visualization",
            "summary": self.visualization.get("summary") or spec.get("summary"),
            "data_as_of": self.visualization.get("data_as_of") or spec.get("data_as_of"),
            "data_table": self.visualization.get("data_table") or spec.get("data_table") or spec.get("data") or [],
            "report_section": self.domain,
            "report_selection_reason": self.reason,
            "snapshot_hash": self.snapshot_hash,
        }


def select_conversation_visualizations(
    db,
    *,
    session_id: str,
    scope_kind: str,
    scope_project_ids: list[str] | None = None,
    selection_text: str | None = None,
) -> tuple[list[SelectedVisualization], list[dict]]:
    target_ids = {str(item) for item in (scope_project_ids or []) if item}
    requested_domains = _requested_domains(selection_text)
    excluded_terms = _excluded_terms(selection_text)
    excluded_domains = _excluded_domains(selection_text)
    candidates: list[SelectedVisualization] = []
    excluded: list[dict] = []
    messages = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session_id,
        models.ChatMessage.role == "assistant",
        models.ChatMessage.status == "completed",
    ).order_by(models.ChatMessage.created_at.asc(), models.ChatMessage.id.asc()).all()

    for message in messages:
        for index, raw in enumerate(message.visualizations or []):
            if not isinstance(raw, dict) or not isinstance(raw.get("spec"), dict):
                continue
            title = str(raw.get("title") or raw["spec"].get("title") or f"Chart {index + 1}")
            inclusion = str(raw.get("report_inclusion") or "auto").casefold()
            domain = classify_domain(raw)
            chart_ids = _project_ids(message, raw)
            reason = "explicitly included"
            if inclusion == "exclude":
                excluded.append({"title": title, "reason": "explicitly excluded"})
                continue
            if inclusion != "include":
                scope_relevant = (
                    (scope_kind == "project" and bool(chart_ids & target_ids))
                    or (scope_kind == "comparison" and bool(chart_ids) and chart_ids.issubset(target_ids))
                    or (scope_kind == "portfolio" and not chart_ids)
                )
                if not scope_relevant:
                    excluded.append({"title": title, "reason": "outside the report scope"})
                    continue
                searchable = _searchable_text(raw)
                if domain in excluded_domains or (excluded_terms and any(term in searchable for term in excluded_terms)):
                    excluded.append({"title": title, "reason": "excluded by the report request"})
                    continue
                if requested_domains and domain not in requested_domains:
                    excluded.append({"title": title, "reason": "not relevant to the requested report topics"})
                    continue
                reason = "automatically selected for scope and topic relevance"
            snapshot_hash = visualization_hash(raw)
            candidates.append(SelectedVisualization(message.id, index, snapshot_hash, raw, domain, reason))

    # Remove exact duplicate saved snapshots while retaining the most recent occurrence.
    unique: dict[str, SelectedVisualization] = {}
    for candidate in candidates:
        unique[candidate.snapshot_hash] = candidate
    selected = list(unique.values())
    last_count = _last_requested_count(selection_text)
    if last_count is not None:
        selected = selected[-last_count:]
    if len(selected) > MAX_REPORT_VISUALIZATIONS:
        omitted = selected[:-MAX_REPORT_VISUALIZATIONS]
        excluded.extend({"title": item.report_payload()["title"], "reason": "report chart limit"} for item in omitted)
        selected = selected[-MAX_REPORT_VISUALIZATIONS:]
    return selected, excluded


def resolve_visualization_references(db, *, session_id: str, references: list[dict]) -> list[dict]:
    resolved: list[dict] = []
    for reference in references:
        message = db.query(models.ChatMessage).filter(
            models.ChatMessage.id == reference.get("m"),
            models.ChatMessage.session_id == session_id,
            models.ChatMessage.role == "assistant",
        ).first()
        index = reference.get("i")
        if message is None or not isinstance(index, int) or index < 0:
            raise ValueError("A report chart snapshot is no longer available. Create a new preview.")
        visualizations = message.visualizations or []
        if index >= len(visualizations) or not isinstance(visualizations[index], dict):
            raise ValueError("A report chart snapshot is no longer available. Create a new preview.")
        raw = visualizations[index]
        if visualization_hash(raw) != reference.get("h"):
            raise ValueError("A report chart changed after preview. Create a new preview.")
        resolved.append(SelectedVisualization(
            message.id, index, reference["h"], raw, classify_domain(raw), "frozen at preview"
        ).report_payload())
    return resolved
