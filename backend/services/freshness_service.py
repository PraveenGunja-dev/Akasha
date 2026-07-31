"""Shared source freshness semantics and durable successful-sync versions."""

from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import re
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

import models


SOURCE_TABLES = {
    "P6": ("p6_project", "p6_activity", "p6_wbs_node"),
    "SAP": ("mt_poamount", "mt_inventory", "mt_materialdocument"),
    "TC": ("tc_network_edge", "tc_network_node", "tc_project_entry"),
    "Pulse": ("pulse_nc", "pulse_rfi"),
    "Mapping": ("project_mapping",),
    "Capacity": ("project_mapping", "p6_project", "p6_activity"),
}

TABLE_SOURCE_SYSTEM = {
    "p6_project": "P6",
    "p6_activity": "P6",
    "p6_wbs_node": "P6",
    "mt_poamount": "SAP",
    "mt_inventory": "SAP",
    "mt_materialdocument": "SAP",
    "tc_network_edge": "TC",
    "tc_network_node": "TC",
    "tc_project_entry": "TC",
    "pulse_nc": "Pulse",
    "pulse_rfi": "Pulse",
    "project_mapping": "Mapping",
    "notifications": "Application",
}


@dataclass(frozen=True)
class SourceFreshness:
    """Freshness for one source; cutoff and ingestion time are never interchangeable."""

    source_system: str
    data_as_of: datetime | None
    last_synced_at: datetime | None
    sync_version: int | None = None


@dataclass(frozen=True)
class SourceEvidence:
    """Immutable evidence reference tied to one source freshness snapshot."""

    evidence_id: str
    source_entity: str
    freshness: SourceFreshness
    record_ids: tuple[str, ...] = ()
    project_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_ids", tuple(self.record_ids))

    @property
    def source_system(self) -> str:
        return self.freshness.source_system

    @property
    def data_as_of(self) -> datetime | None:
        return self.freshness.data_as_of

    @property
    def last_synced_at(self) -> datetime | None:
        return self.freshness.last_synced_at

    @property
    def sync_version(self) -> int | None:
        return self.freshness.sync_version


@dataclass(frozen=True)
class FreshnessEnvelope:
    """Per-source freshness captured when an answer is generated."""

    sources: tuple[SourceFreshness, ...]
    answer_generated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))


def make_freshness_envelope(
    sources: Iterable[SourceFreshness],
    *,
    answer_generated_at: datetime | None = None,
) -> FreshnessEnvelope:
    return FreshnessEnvelope(
        sources=tuple(sources),
        answer_generated_at=answer_generated_at or datetime.utcnow(),
    )


def get_source_freshness(db: Session, source_system: str) -> SourceFreshness | None:
    state = db.get(models.SourceSyncState, _source_name(source_system))
    if state is None:
        return None
    return _to_dto(state)


def get_sync_versions(db: Session, source_systems: Iterable[str] | None = None) -> dict[str, int]:
    query = db.query(models.SourceSyncState)
    if source_systems is not None:
        names = tuple(dict.fromkeys(_source_name(name) for name in source_systems))
        if not names:
            return {}
        query = query.filter(models.SourceSyncState.source_system.in_(names))
    return {row.source_system: row.sync_version for row in query.all()}


def cache_version_token(db: Session, source_systems: Iterable[str]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted(get_sync_versions(db, source_systems).items()))


def build_answer_provenance(
    db: Session,
    tool_names: Iterable[str],
    *,
    evidence: Iterable[Mapping[str, Any]] = (),
    answer_generated_at: datetime | None = None,
) -> dict:
    """Build persisted provenance from evidence emitted by actual tool results."""
    tools = tuple(dict.fromkeys(name for name in tool_names if name))
    normalized_evidence = _deduplicate_evidence(evidence)
    source_names = tuple(dict.fromkeys(
        item["source_system"] for item in normalized_evidence if item.get("source_system")
    ))
    states = {
        state.source_system: state
        for state in db.query(models.SourceSyncState).filter(
            models.SourceSyncState.source_system.in_(source_names)
        ).all()
    } if source_names else {}
    systems = []
    for source_name in source_names:
        state = states.get(source_name)
        source_evidence = [
            item for item in normalized_evidence if item.get("source_system") == source_name
        ]
        tables = sorted({item["source_entity"] for item in source_evidence})
        evidence_cutoffs = [item.get("data_as_of") for item in source_evidence if item.get("data_as_of")]
        evidence_sync_times = [
            item.get("last_synced_at") for item in source_evidence if item.get("last_synced_at")
        ]
        systems.append({
            "source_system": source_name,
            "tables": tables,
            "data_as_of": min(evidence_cutoffs, default=_iso(state.data_as_of if state else None)),
            "last_synced_at": max(evidence_sync_times, default=_iso(state.last_synced_at if state else None)),
            "sync_version": state.sync_version if state else None,
        })
        for item in source_evidence:
            if item.get("sync_version") is None and state is not None:
                item["sync_version"] = state.sync_version
    generated_at = answer_generated_at or datetime.utcnow()
    data_cutoffs = [item["data_as_of"] for item in systems if item["data_as_of"]]
    sync_times = [item["last_synced_at"] for item in systems if item["last_synced_at"]]
    return {
        "tools": list(tools),
        "tables": sorted({table for item in systems for table in item["tables"]}),
        "systems": systems,
        "evidence": normalized_evidence,
        "data_as_of": min(data_cutoffs, default=None),
        "last_synced_at": max(sync_times, default=None),
        "answer_generated_at": generated_at.isoformat(),
    }


def extract_tool_evidence(
    data: Any,
    *,
    tool_name: str,
    status: str,
    project_id: str | None = None,
) -> tuple[dict[str, Any], ...]:
    """Normalize only explicit provenance fields from one tool result."""
    if status == "error":
        return ()

    root = data if isinstance(data, Mapping) else {}
    source_nodes = _source_nodes(data)
    for table in _implicit_source_tables(tool_name, root):
        source_nodes.setdefault(table, []).append(root)
    if not source_nodes:
        return ()
    resolved_project_id = project_id or root.get("project_id")
    evidence = []
    for table, nodes in source_nodes.items():
        source_system = TABLE_SOURCE_SYSTEM.get(table)
        if source_system is None:
            continue
        data_as_of = _evidence_timestamp(root, nodes, table, "data_as_of")
        last_synced_at = _evidence_timestamp(root, nodes, table, "last_synced_at")
        record_ids = _record_ids(data, table)
        identity = {
            "tool_name": tool_name,
            "status": status,
            "source_system": source_system,
            "source_entity": table,
            "project_id": str(resolved_project_id) if resolved_project_id else None,
            "record_ids": record_ids,
            "data_as_of": str(data_as_of) if data_as_of else None,
            "last_synced_at": str(last_synced_at) if last_synced_at else None,
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        evidence.append({"evidence_id": f"sha256:{digest}", **identity})
    return tuple(evidence)


def mark_source_sync_succeeded(
    db: Session,
    source_system: str,
    *,
    data_as_of: datetime | None = None,
    last_synced_at: datetime | None = None,
) -> SourceFreshness:
    """Atomically persist a successful sync and increment its cache version."""
    source_system = _source_name(source_system)
    last_synced_at = last_synced_at or datetime.utcnow()
    values = {
        "source_system": source_system,
        "sync_version": 1,
        "data_as_of": data_as_of,
        "last_synced_at": last_synced_at,
    }

    try:
        dialect = db.get_bind().dialect.name
        if dialect == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        elif dialect == "sqlite":
            from sqlalchemy.dialects.sqlite import insert
        else:
            insert = None

        if insert is not None:
            statement = insert(models.SourceSyncState).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=[models.SourceSyncState.source_system],
                set_={
                    "sync_version": models.SourceSyncState.sync_version + 1,
                    "data_as_of": data_as_of,
                    "last_synced_at": last_synced_at,
                },
            )
            db.execute(statement)
        else:
            updated = db.query(models.SourceSyncState).filter_by(
                source_system=source_system
            ).update({
                models.SourceSyncState.sync_version: models.SourceSyncState.sync_version + 1,
                models.SourceSyncState.data_as_of: data_as_of,
                models.SourceSyncState.last_synced_at: last_synced_at,
            })
            if not updated:
                db.add(models.SourceSyncState(**values))

        db.commit()
        return _to_dto(db.get(models.SourceSyncState, source_system))
    except Exception:
        db.rollback()
        raise


def _source_name(source_system: str) -> str:
    source_system = source_system.strip()
    if not source_system:
        raise ValueError("source_system must not be empty")
    return source_system


def _explicit_source_tables(data: Mapping[str, Any]) -> tuple[str, ...]:
    values = []
    for key in ("_source_table", "_source_tables", "_sources_used"):
        value = data.get(key)
        values.extend(value if isinstance(value, (list, tuple, set)) else [value])
    provenance = data.get("provenance")
    if isinstance(provenance, Mapping):
        source_tables = provenance.get("source_tables")
        values.extend(source_tables if isinstance(source_tables, (list, tuple, set)) else [source_tables])
    tables = []
    for value in values:
        if not isinstance(value, str):
            continue
        tables.extend(part for part in re.split(r"[,+\s]+", value.strip()) if part)
    return tuple(dict.fromkeys(tables))


def _source_nodes(data: Any) -> dict[str, list[Mapping[str, Any]]]:
    nodes: dict[str, list[Mapping[str, Any]]] = {}

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            p6_unavailable = value.get("p6_available") is False
            for table in _explicit_source_tables(value):
                if p6_unavailable and table.startswith("p6_"):
                    continue
                nodes.setdefault(table, []).append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(data)
    return nodes


def _implicit_source_tables(tool_name: str, data: Mapping[str, Any]) -> tuple[str, ...]:
    if tool_name.startswith("capacity_"):
        tables = ["project_mapping"]
        metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
        counts = metadata.get("evidence") if isinstance(metadata.get("evidence"), Mapping) else {}
        if data.get("p6_available") is True or (counts.get("p6_project_count") or 0) > 0:
            tables.extend(("p6_project", "p6_activity"))
        return tuple(tables)
    if tool_name == "portfolio_get_notifications":
        return ("notifications",)
    if tool_name != "risk_get_metric" or data.get("availability") is False:
        return ()
    metric_id = str(data.get("metric_id"))
    if metric_id in {
        "project360.risk_flags", "project360.cod_risk", "project360.status_tier",
    }:
        components = data.get("components") if isinstance(data.get("components"), Mapping) else {}
        tables = []
        if any(components.get(key) is not None for key in (
            "progress_pct", "schedule_variance_days", "spi",
        )) or (metric_id == "project360.cod_risk" and (components.get("delay_days") or 0) > 0):
            tables.append("p6_project")
        if any(components.get(key) is not None for key in (
            "material_availability_pct", "po_volume", "ordered_quantity", "in_transit_volume",
        )):
            tables.append("mt_poamount")
        return tuple(tables)
    return tuple({
        "pmag.schedule_rag": ("p6_project",),
        "command_center.schedule_risk_count": ("p6_project",),
        "command_center.financial_risk_count": ("mt_poamount",),
        "command_center.overall_risk_score": ("p6_project", "mt_poamount"),
        "command_center.risk_heatmap": ("p6_project",),
        "project360.status_tier_counts": ("p6_project", "mt_poamount", "tc_network_edge"),
        "predictive.portfolio_slippage": ("p6_project",),
        "kpi.project_exposure": ("p6_activity", "mt_poamount", "tc_network_edge"),
    }.get(metric_id, ()))


def _evidence_timestamp(
    root: Mapping[str, Any],
    nodes: list[Mapping[str, Any]],
    table: str,
    field: str,
):
    candidates = [root, *nodes]
    for value in candidates:
        provenance = value.get("provenance") if isinstance(value.get("provenance"), Mapping) else {}
        raw_freshness = value.get("freshness")
        freshness = raw_freshness if isinstance(raw_freshness, Mapping) else {}
        metadata = value.get("metadata") if isinstance(value.get("metadata"), Mapping) else {}
        metadata_freshness = (
            metadata.get("freshness") if isinstance(metadata.get("freshness"), Mapping) else {}
        )
        if field == "data_as_of":
            found = _first_value(
                provenance.get("data_as_of"), freshness.get("data_as_of"),
                metadata_freshness.get("data_as_of"), value.get("data_as_of"),
                value.get("data_date"),
            )
        else:
            source_key = {"pulse_nc": "nc_last_synced_at", "pulse_rfi": "rfi_last_synced_at"}.get(table)
            found = _first_value(
                value.get("_synced_at"), provenance.get(source_key) if source_key else None,
                provenance.get("last_synced_at"), freshness.get(table),
                freshness.get("last_synced_at"), metadata_freshness.get("last_synced_at"),
                raw_freshness if not isinstance(raw_freshness, Mapping) else None,
                value.get("last_synced_at"),
            )
        if found is not None:
            return found
    return None


def _record_ids(data: Any, table: str) -> list[str]:
    ids = []

    def visit(value: Any) -> None:
        if len(ids) >= 100:
            return
        if isinstance(value, Mapping):
            provenance = value.get("provenance")
            key = {"pulse_nc": "nc_source_ids", "pulse_rfi": "rfi_source_ids"}.get(table)
            if key and isinstance(provenance, Mapping) and isinstance(provenance.get(key), (list, tuple)):
                ids.extend(str(item) for item in provenance[key] if item is not None)
            id_key = "activity_id" if table == "p6_activity" else "edge_id" if table == "tc_network_edge" else None
            if id_key and value.get(id_key) is not None:
                ids.append(str(value[id_key]))
            collection_key = (
                "activity_ids" if table == "p6_activity"
                else "wbs_object_ids" if table == "p6_wbs_node"
                else None
            )
            if collection_key and isinstance(value.get(collection_key), (list, tuple)):
                ids.extend(str(item) for item in value[collection_key] if item is not None)
            for child in value.values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(data)
    return list(dict.fromkeys(ids))[:100]


def _deduplicate_evidence(evidence: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique = {}
    for item in evidence:
        if not isinstance(item, Mapping) or not item.get("source_entity"):
            continue
        value = dict(item)
        key = value.get("evidence_id") or json.dumps(value, sort_keys=True, default=str)
        unique[key] = value
    return list(unique.values())


def _first_value(*values):
    return next((value for value in values if value is not None), None)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _to_dto(state: models.SourceSyncState) -> SourceFreshness:
    return SourceFreshness(
        source_system=state.source_system,
        data_as_of=state.data_as_of,
        last_synced_at=state.last_synced_at,
        sync_version=state.sync_version,
    )
