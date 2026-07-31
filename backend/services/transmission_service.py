"""Canonical transmission snapshots, associations, and DTOs."""

import ast
import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

import models


_NEGATIVE_STATUSES = {
    "delayed": "delayed",
    "delay": "delayed",
    "blocked": "blocked",
    "cancelled": "cancelled",
    "canceled": "cancelled",
    "on_hold": "on_hold",
    "hold": "on_hold",
}
_CANONICAL_STATUSES = {
    "completed": "completed",
    "complete": "completed",
    "commissioned": "completed",
    "charged": "completed",
    "energized": "completed",
    "in_progress": "in_progress",
    "under_progress": "in_progress",
    "ongoing": "in_progress",
    "not_started": "not_started",
    "yet_to_start": "not_started",
}


def normalize_region(value) -> str:
    text = " ".join(str(value or "").split())
    known = {"khavda": "Khavda", "rajasthan": "Rajasthan"}
    return known.get(text.casefold(), text)


def _normalized_key(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def _record_rank(record):
    return (record.upload_time or datetime.min, record.id or -1)


def _latest(records, key):
    selected = {}
    for record in records:
        record_key = key(record)
        current = selected.get(record_key)
        if current is None or _record_rank(record) > _record_rank(current):
            selected[record_key] = record
    return list(selected.values())


@dataclass(frozen=True)
class TransmissionSnapshot:
    mappings: tuple
    entries: tuple
    edges: tuple
    nodes: tuple

    @classmethod
    def load(cls, db: Session) -> "TransmissionSnapshot":
        return cls(
            mappings=tuple(db.query(models.ProjectMapping).all()),
            entries=tuple(db.query(models.TcProjectEntry).all()),
            edges=tuple(db.query(models.TcNetworkEdge).all()),
            # Project association snapshots do not need topology nodes.
            nodes=(),
        )


def build_transmission_snapshot(db: Session) -> TransmissionSnapshot:
    return TransmissionSnapshot.load(db)


def latest_direct_edges(db: Session) -> list:
    """Latest row for each region/line/mapping association."""
    return _latest(
        db.query(models.TcNetworkEdge).all(),
        lambda edge: (
            _normalized_key(edge.region),
            _normalized_key(edge.edge_id),
            edge.mapping_id,
        ),
    )


def latest_physical_edges(db: Session, region: str | None = None) -> list:
    """Latest physical line, independent of mapping fan-out."""
    edges = latest_direct_edges(db)
    if region is not None:
        wanted = _normalized_key(region)
        edges = [edge for edge in edges if _normalized_key(edge.region) == wanted]
    return sorted(
        _latest(
            edges,
            lambda edge: (_normalized_key(edge.region), _normalized_key(edge.edge_id)),
        ),
        key=lambda edge: (_normalized_key(edge.region), _normalized_key(edge.edge_id)),
    )


def latest_nodes(db: Session, region: str | None = None) -> list:
    nodes = db.query(models.TcNetworkNode).all()
    if region is not None:
        wanted = _normalized_key(region)
        nodes = [node for node in nodes if _normalized_key(node.region) == wanted]
    return sorted(
        _latest(
            nodes,
            lambda node: (_normalized_key(node.region), _normalized_key(node.node_id)),
        ),
        key=lambda node: (_normalized_key(node.region), _normalized_key(node.node_id)),
    )


def latest_project_entries(db: Session, region: str | None = None) -> list:
    entries = db.query(models.TcProjectEntry).all()
    if region is not None:
        wanted = _normalized_key(region)
        entries = [entry for entry in entries if _normalized_key(entry.region) == wanted]
    return sorted(
        _latest(
            entries,
            lambda entry: (
                _normalized_key(entry.region),
                entry.mapping_id,
                _normalized_key(entry.block),
            ),
        ),
        key=lambda entry: (
            _normalized_key(entry.region),
            entry.mapping_id if entry.mapping_id is not None else -1,
            _normalized_key(entry.block),
        ),
    )


def _values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        result = []
        for nested in value.values():
            result.extend(_values(nested))
        return result
    if isinstance(value, (list, tuple, set)):
        result = []
        for nested in value:
            result.extend(_values(nested))
        return result
    text = str(value).strip()
    if not text or text.casefold() in {"none", "null", "nan"}:
        return []
    return [part.strip() for part in re.split(r"[,;|]", text) if part.strip()]


def parse_projects_phases(value) -> dict[str, list[str]]:
    """Parse current JSON and legacy Python-literal/plain association values."""
    parsed = value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {"projects": [], "phases": []}
        for loader in (json.loads, ast.literal_eval):
            try:
                parsed = loader(text)
                break
            except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
                parsed = text

    projects = []
    phases = []
    if isinstance(parsed, dict):
        for key, nested in parsed.items():
            normalized = str(key).strip().casefold()
            if normalized in {"phase", "phases"}:
                phases.extend(_values(nested))
            elif normalized in {"project", "projects"}:
                projects.extend(_values(nested))
    elif isinstance(parsed, (list, tuple, set)):
        values = _values(parsed)
        projects.extend(values)
        # Legacy dashboard rows stored phase arrays directly in this column.
        phases.extend(values)
    else:
        # Historical rows stored a lone phase in the projects column.
        plain = _values(parsed)
        projects.extend(plain)
        phases.extend(plain)

    return {
        "projects": list(dict.fromkeys(projects)),
        "phases": list(dict.fromkeys(phases)),
    }


def _entry_phases(entries) -> set[str]:
    phases = set()
    for entry in entries:
        parsed = parse_projects_phases(entry.phase)
        values = parsed["phases"] or parsed["projects"]
        phases.update(_normalized_key(value) for value in values if value)
    return phases


def filter_edges_by_kps(edges, project_entries):
    """Apply the approved KPS narrowing after direct/phase association."""
    roman = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V"}
    kps_nodes = set()
    for entry in project_entries:
        value = str(entry.kps or "").strip().upper()
        if not value:
            continue
        suffix = value.split("-", 1)[1] if "-" in value else value.replace("KPS", "").strip()
        kps_nodes.add(f"KPS-{roman.get(suffix, suffix)}")
    if not kps_nodes:
        return edges
    touching = [
        edge for edge in edges
        if any(
            kps in str(label or "").upper()
            for edge_label in (edge.from_label, edge.to_label, edge.from_node, edge.to_node)
            for kps in kps_nodes
            for label in (edge_label,)
        )
    ]
    return touching or edges


def project_edges(
    db: Session,
    project_id: str,
    snapshot: TransmissionSnapshot | None = None,
) -> tuple[object | None, list, list]:
    if snapshot is None:
        mappings = db.query(models.ProjectMapping).filter(
            models.ProjectMapping.project_id == project_id
        ).order_by(models.ProjectMapping.id.asc()).all()
        latest_entries = latest_project_entries(db)
        direct_edges = latest_direct_edges(db)
    else:
        mappings = sorted(
            (mapping for mapping in snapshot.mappings if mapping.project_id == project_id),
            key=lambda mapping: mapping.id,
        )
        latest_entries = _latest(
            snapshot.entries,
            lambda entry: (_normalized_key(entry.region), entry.mapping_id, _normalized_key(entry.block)),
        )
        direct_edges = _latest(
            snapshot.edges,
            lambda edge: (_normalized_key(edge.region), _normalized_key(edge.edge_id), edge.mapping_id),
        )
    if not mappings:
        return None, [], []

    mapping = mappings[0]
    mapping_ids = {item.id for item in mappings}

    entries = [
        entry for entry in latest_entries
        if entry.mapping_id in mapping_ids
    ]
    phases = _entry_phases(entries)
    union = []
    for edge in direct_edges:
        edge_phases = {
            _normalized_key(value)
            for value in parse_projects_phases(edge.projects)["phases"]
        }
        if edge.mapping_id in mapping_ids or (phases and phases.intersection(edge_phases)):
            union.append(edge)

    # Preserve the approved behavior: KPS is applied to the complete phase/direct union.
    union = filter_edges_by_kps(union, entries)
    edges = _latest(
        union,
        lambda edge: (_normalized_key(edge.region), _normalized_key(edge.edge_id)),
    )
    edges.sort(key=lambda edge: (_normalized_key(edge.region), _normalized_key(edge.edge_id)))
    return mapping, entries, edges


def project_status(db: Session, project_id: str) -> dict:
    """Return the canonical project-scoped transmission summary and line DTOs."""
    mapping, _, edges = project_edges(db, project_id)
    project_name = (
        mapping.project_name_from_p6 or mapping.project or project_id
        if mapping else project_id
    )
    lines = [edge_dict(edge) for edge in edges]
    counts = {status: 0 for status in ("completed", "in_progress", "not_started", "unknown")}
    for line in lines:
        status = line["canonical_status"]
        counts[status if status in counts else "unknown"] += 1
    readiness = readiness_from_counts(
        total_lines=len(lines),
        completed=counts["completed"],
        in_progress=counts["in_progress"],
        not_started=counts["not_started"],
        unknown=counts["unknown"],
        delayed=sum(bool(line["is_delayed"]) for line in lines),
    )
    latest = max((line["upload_time"] for line in lines if line["upload_time"]), default=None)
    return {
        "project_id": project_id,
        "project_name": project_name,
        "has_data": bool(lines),
        "total_lines": len(lines),
        **counts,
        "delayed": sum(bool(line["is_delayed"]) for line in lines),
        **readiness,
        "lines": lines,
        "last_synced_at": latest,
    }


def readiness_from_counts(
    *,
    total_lines: int,
    completed: int,
    in_progress: int,
    not_started: int,
    unknown: int,
    delayed: int,
) -> dict:
    """Classify transmission readiness from canonical physical-line states."""
    if total_lines <= 0:
        return {
            "readiness_status": "Unavailable",
            "readiness_pct": None,
            "readiness_formula": "completed physical lines / total physical lines",
        }
    readiness_pct = round(completed / total_lines * 100, 1)
    if delayed:
        status = "At Risk"
    elif completed == total_lines:
        status = "Ready"
    elif in_progress:
        status = "In Progress"
    elif not_started:
        status = "Not Ready"
    else:
        status = "Unknown"
    return {
        "readiness_status": status,
        "readiness_pct": readiness_pct,
        "readiness_formula": "completed physical lines / total physical lines",
    }


def network_status(db: Session) -> dict:
    """Return canonical portfolio transmission status counts."""
    edges = latest_physical_edges(db)
    return {
        "total_lines": len(edges),
        "delayed_lines": sum(bool(edge.is_delayed) for edge in edges),
    }


def parse_progress(value) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).strip().replace("%", ""))
    except (TypeError, ValueError):
        return None


def average_progress(edge) -> float | None:
    values = [parse_progress(edge.foundation), parse_progress(edge.erection), parse_progress(edge.stringing)]
    available = [value for value in values if value is not None]
    return round(sum(available) / len(available), 1) if available else None


def canonical_status(edge) -> str:
    status = _normalized_key(edge.normalized_status or edge.status).replace("-", "_").replace(" ", "_")
    progress = average_progress(edge)
    progress_parts = [parse_progress(edge.foundation), parse_progress(edge.erection), parse_progress(edge.stringing)]
    # Explicit negative states must win over progress percentages and words such
    # as "complete" embedded in a delayed/blocked source status.
    for source, canonical in _NEGATIVE_STATUSES.items():
        if source in status:
            return canonical
    if status in _CANONICAL_STATUSES:
        return _CANONICAL_STATUSES[status]
    if progress is not None and progress > 0:
        return "in_progress"
    if all(value is not None for value in progress_parts) and progress == 0:
        return "not_started"
    return "unknown"


def parse_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text or text.casefold() in {"none", "null", "nan", "-"}:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for fmt in ("%b-%y", "%B-%y", "%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y", "%m/%Y", "%Y-%m"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def delay_days(edge) -> int | None:
    expected = parse_date(edge.expected_date)
    scheduled = parse_date(edge.scd)
    if expected is None or scheduled is None:
        return None
    return max((expected - scheduled).days, 0)


def edge_dict(edge) -> dict:
    associations = parse_projects_phases(edge.projects)
    foundation = parse_progress(edge.foundation)
    erection = parse_progress(edge.erection)
    stringing = parse_progress(edge.stringing)
    expected = parse_date(edge.expected_date)
    scheduled = parse_date(edge.scd)
    charged = parse_date(edge.charged_date)
    return {
        "edge_id": edge.edge_id,
        "region": normalize_region(edge.region),
        "from_node": edge.from_node,
        "from_label": edge.from_label,
        "to_node": edge.to_node,
        "to_label": edge.to_label,
        "status": edge.status,
        "normalized_status": edge.normalized_status,
        "canonical_status": canonical_status(edge),
        "contractor": edge.contractor,
        "projects": associations["projects"],
        "phases": associations["phases"],
        "voltage": edge.voltage,
        "length": edge.length,
        "foundation": edge.foundation,
        "erection": edge.erection,
        "stringing": edge.stringing,
        "foundation_pct": foundation,
        "erection_pct": erection,
        "stringing_pct": stringing,
        "avg_progress": average_progress(edge),
        "is_delayed": bool(edge.is_delayed),
        "expected_date": edge.expected_date,
        "scd": edge.scd,
        "charged_date": edge.charged_date,
        "expected_date_iso": expected.isoformat() if expected else None,
        "scd_iso": scheduled.isoformat() if scheduled else None,
        "charged_date_iso": charged.isoformat() if charged else None,
        "days_delayed": delay_days(edge),
        "mapping_id": edge.mapping_id,
        "upload_time": edge.upload_time.isoformat() if edge.upload_time else None,
    }


def node_dict(node) -> dict:
    return {
        "id": node.node_id,
        "label": node.label,
        "type": node.type,
        "status": node.status,
        "x": node.x,
        "y": node.y,
    }


def freshness(
    db: Session,
    region: str | None = None,
    snapshot: TransmissionSnapshot | None = None,
) -> dict:
    if snapshot is None:
        edges = latest_physical_edges(db, region)
    else:
        edges = _latest(
            snapshot.edges,
            lambda edge: (_normalized_key(edge.region), _normalized_key(edge.edge_id)),
        )
        if region is not None:
            edges = [edge for edge in edges if _normalized_key(edge.region) == _normalized_key(region)]
    latest = max((edge.upload_time for edge in edges if edge.upload_time), default=None)
    return {
        "synced_at": latest.isoformat() if latest else None,
        "exists": latest is not None,
        "region": normalize_region(region) if region is not None else None,
    }


def region_network(db: Session, region: str) -> dict:
    edges = latest_physical_edges(db, region)
    return {
        "nodes": [node_dict(node) for node in latest_nodes(db, region)],
        "edges": [edge_dict(edge) for edge in edges],
        "freshness": freshness(db, region),
    }
