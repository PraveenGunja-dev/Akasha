"""Shared project-scoped SAP record selection and aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

import models
from services.project_catalog_service import list_project_mappings


_EMPTY_MARKERS = {"", "nan", "none", "null"}
_ISSUE_MOVEMENTS = {"221", "261"}
_REVERSAL_MOVEMENTS = {"222", "262"}
_SOURCES = {
    "mt_poamount": models.MTPOAmount,
    "mt_inventory": models.MTInventory,
    "mt_materialdocument": models.MTMaterialDocument,
}


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return None if cleaned.lower() in _EMPTY_MARKERS else cleaned


def _number(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _is_wbs_member(value: Any, root: str) -> bool:
    value = _clean(value)
    return bool(value and (value == root or any(value.startswith(root + delimiter) for delimiter in ".-/")))


def wbs_membership(column, root: str):
    """SQL equivalent of the exact or delimiter-bounded WBS rule."""
    escaped = root.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return or_(
        column == root,
        column.like(f"{escaped}.%", escape="\\"),
        column.like(f"{escaped}-%", escape="\\"),
        column.like(f"{escaped}/%", escape="\\"),
    )


@dataclass(frozen=True)
class SapProjectSnapshot:
    """One bulk read reused for all project calculations in a request."""

    mappings: tuple
    scopes: tuple
    records: dict[str, tuple]
    scope_matches: dict[str, dict[int, dict[int, float]]]

    @classmethod
    def load(cls, db: Session, mappings: Iterable | None = None) -> "SapProjectSnapshot":
        catalog = tuple(mappings) if mappings is not None else tuple(list_project_mappings(db))
        scopes = tuple(
            db.query(models.SapProjectScope).filter(
                models.SapProjectScope.active.is_(True)
            ).all()
        )
        records = {name: tuple(db.query(model).all()) for name, model in _SOURCES.items()}
        return cls(
            mappings=catalog,
            scopes=scopes,
            records=records,
            scope_matches=_index_scope_matches(scopes, records),
        )

    def project_mappings(self, project_id: str) -> list:
        return [mapping for mapping in self.mappings if mapping.project_id == project_id]

    def allocation(self, mapping, plant: str, field: str) -> tuple[float, float]:
        # Only catalog mappings eligible for plant fallback belong in the
        # denominator. WBS-owned and demo mappings are excluded by construction.
        eligible = [
            item for item in self.mappings
            if not _clean(item.module_wbs) and _clean(getattr(item, field, None)) == plant
        ]
        capacities: dict[str, float] = {}
        for item in eligible:
            identity = item.project_id or f"mapping:{item.id}"
            capacities[identity] = max(capacities.get(identity, 0.0), _number(item.capacity_mwac))
        identity = mapping.project_id or f"mapping:{mapping.id}"
        project_capacity = capacities.get(identity, _number(mapping.capacity_mwac))
        shared_capacity = sum(capacities.values())
        return (
            project_capacity / shared_capacity if shared_capacity > 0 else 1.0,
            shared_capacity,
        )


def build_sap_snapshot(db: Session, mappings: Iterable | None = None) -> SapProjectSnapshot:
    return SapProjectSnapshot.load(db, mappings)


def _freshness(records: list) -> str | None:
    latest = max((row.upload_time for row in records if row.upload_time), default=None)
    return latest.isoformat() if latest else None


def _values(records: list, field: str) -> set[str]:
    return {value for row in records if (value := _clean(getattr(row, field, None)))}


def _unit_metadata(pos: list, inventory: list, documents: list) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    currencies = _values(pos, "currency")
    inventory_units = _values(inventory, "base_unit")
    document_units = _values(documents, "base_unit")
    if pos:
        warnings.append("PO quantity unit is unavailable in mt_poamount.")
        if not currencies:
            warnings.append("PO value currency is unavailable.")
        elif any(not _clean(row.currency) for row in pos):
            warnings.append("Some PO rows have no value currency.")
        elif len(currencies) > 1:
            warnings.append("PO values contain mixed currencies and must not be treated as one currency total.")
    for rows, units, label in (
        (inventory, inventory_units, "Inventory"),
        (documents, document_units, "Material document"),
    ):
        if rows and not units:
            warnings.append(f"{label} quantity unit is unavailable.")
        elif any(not _clean(row.base_unit) for row in rows):
            warnings.append(f"Some {label.lower()} rows have no quantity unit.")
        elif len(units) > 1:
            warnings.append(f"{label} quantities contain mixed units and are not directly additive.")
    if inventory and any(_number(row.value_unrestricted) for row in inventory):
        warnings.append("Inventory value currency is unavailable in mt_inventory.")
    if documents and any(_number(row.amount_in_lc) for row in documents):
        warnings.append("Material document local currency code is unavailable.")
    return {
        "po_quantity_units": [],
        "po_value_currencies": sorted(currencies),
        "inventory_quantity_units": sorted(inventory_units),
        "material_document_quantity_units": sorted(document_units),
        "inventory_value_currency": None,
        "material_document_value_currency": None,
    }, warnings


def _select_source(snapshot: SapProjectSnapshot, mappings: list, source: str) -> tuple[list, dict[int, float], dict]:
    if snapshot.scopes:
        return _select_master_scopes(snapshot, mappings, source)

    rows = snapshot.records[source]
    wbs_roots = list(dict.fromkeys(_clean(item.module_wbs) for item in mappings if _clean(item.module_wbs)))
    if wbs_roots:
        selected = [row for row in rows if any(_is_wbs_member(row.wbs_element, root) for root in wbs_roots)]
        return selected, {row.id: 1.0 for row in selected}, {
            "type": "wbs", "wbs": wbs_roots[0], "wbs_roots": wbs_roots,
            "selected_plant": None, "plant_source": None, "allocation_ratio": 1.0,
            "shared_plant_capacity_mwac": None,
        }

    selected_by_id: dict[int, object] = {}
    weights: dict[int, float] = {}
    scopes = []
    for mapping in mappings:
        spv = _clean(mapping.spv_plant_code)
        agel = _clean(mapping.agel)
        if spv and any(_clean(row.plant_code) == spv for row in rows):
            plant, field = spv, "spv_plant_code"
        elif agel and any(_clean(row.plant_code) == agel for row in rows):
            plant, field = agel, "agel"
        else:
            continue
        ratio, shared = snapshot.allocation(mapping, plant, field)
        scopes.append((plant, field, ratio, shared))
        for row in rows:
            if _clean(row.plant_code) == plant:
                selected_by_id[row.id] = row
                # Duplicate mapping rows must never apply the same allocation twice.
                weights[row.id] = max(weights.get(row.id, 0.0), ratio)
    first = scopes[0] if scopes else (None, None, 1.0, None)
    return list(selected_by_id.values()), weights, {
        "type": "plant" if scopes else "unmapped",
        "wbs": None, "wbs_roots": [], "selected_plant": first[0],
        "plant_source": first[1], "allocation_ratio": first[2],
        "shared_plant_capacity_mwac": first[3],
    }


def _select_master_scopes(
    snapshot: SapProjectSnapshot,
    mappings: list,
    source: str,
) -> tuple[list, dict[int, float], dict]:
    mapping_ids = {mapping.id for mapping in mappings}
    rules = [scope for scope in snapshot.scopes if scope.project_mapping_id in mapping_ids]
    wbs_rules = [scope for scope in rules if scope.match_kind == "wbs_prefix"]
    plant_rules = [scope for scope in rules if scope.match_kind == "plant_code"]
    rows_by_id = {row.id: row for row in snapshot.records[source]}
    weights: dict[int, float] = {}
    for mapping_id in mapping_ids:
        for row_id, weight in snapshot.scope_matches[source].get(mapping_id, {}).items():
            weights[row_id] = max(weights.get(row_id, 0.0), weight)

    matched_kinds = set()
    if weights:
        matched_kinds.add("wbs_prefix" if wbs_rules else "plant_code")
    scope_type = (
        "mixed" if len(matched_kinds) > 1
        else "wbs" if "wbs_prefix" in matched_kinds
        else "plant" if "plant_code" in matched_kinds
        else "unmapped"
    )
    roots = list(dict.fromkeys(rule.match_value for rule in wbs_rules))
    plants = list(dict.fromkeys(rule.match_value for rule in plant_rules))
    return [rows_by_id[row_id] for row_id in weights], weights, {
        "type": scope_type,
        "wbs": roots[0] if len(roots) == 1 else None,
        "wbs_roots": roots,
        "selected_plant": plants[0] if len(plants) == 1 else None,
        "selected_plants": plants,
        "plant_source": "sap_project_scope" if plants else None,
        "allocation_ratio": min(weights.values(), default=1.0),
        "shared_plant_capacity_mwac": None,
        "rules": [
            {
                "owner": rule.owner,
                "match_kind": rule.match_kind,
                "match_value": rule.match_value,
                "allocation_group": rule.allocation_group,
                "allocation_weight": float(rule.allocation_weight or 1.0),
            }
            for rule in rules
        ],
    }


def _index_scope_matches(scopes: tuple, records: dict[str, tuple]) -> dict[str, dict[int, dict[int, float]]]:
    indexed: dict[str, dict[int, dict[int, float]]] = {}
    wbs_mapping_ids = {
        scope.project_mapping_id for scope in scopes if scope.match_kind == "wbs_prefix"
    }
    wbs_rules_by_root: dict[str, list] = {}
    for scope in scopes:
        if scope.match_kind == "wbs_prefix":
            wbs_rules_by_root.setdefault(_clean(scope.match_value), []).append(scope)
    plant_rules_by_code: dict[str, list] = {}
    for scope in scopes:
        if scope.match_kind != "plant_code" or scope.project_mapping_id in wbs_mapping_ids:
            continue
        plant_rules_by_code.setdefault(_clean(scope.match_value), []).append(scope)

    for source, rows in records.items():
        source_matches: dict[int, dict[int, float]] = {}
        for row in rows:
            wbs_value = _clean(row.wbs_element)
            prefixes = {wbs_value} if wbs_value else set()
            if wbs_value:
                prefixes.update(
                    wbs_value[:index]
                    for index, character in enumerate(wbs_value)
                    if character in ".-/" and index > 0
                )
            matches = [
                scope
                for prefix in prefixes
                for scope in wbs_rules_by_root.get(prefix, ())
            ]
            matches.extend(plant_rules_by_code.get(_clean(row.plant_code), ()))
            for scope in matches:
                project_matches = source_matches.setdefault(scope.project_mapping_id, {})
                project_matches[row.id] = max(
                    project_matches.get(row.id, 0.0),
                    float(scope.allocation_weight or 1.0),
                )
        indexed[source] = source_matches
    return indexed


def get_sap_project_data(
    db: Session,
    project_id: str | None,
    snapshot: SapProjectSnapshot | None = None,
    *,
    mapping_id: int | None = None,
) -> dict:
    """Return authoritative, unrounded project aggregates from a reusable snapshot."""
    snapshot = snapshot or build_sap_snapshot(db)
    mappings = (
        [mapping for mapping in snapshot.mappings if mapping.id == mapping_id]
        if mapping_id is not None
        else snapshot.project_mappings(project_id)
    )
    project_name = (
        mappings[0].project_name_from_p6 or mappings[0].project or project_id
        if mappings else project_id
    )
    if not mappings:
        return _empty_result(project_id, project_name)

    selected = {}
    weights = {}
    source_scopes = {}
    for source in _SOURCES:
        selected[source], weights[source], source_scopes[source] = _select_source(snapshot, mappings, source)
    pos = selected["mt_poamount"]
    inventory = selected["mt_inventory"]
    documents = selected["mt_materialdocument"]

    def total(source: str, rows: list, field: str, *, absolute: bool = False) -> float:
        return sum(
            (abs(_number(getattr(row, field))) if absolute else _number(getattr(row, field)))
            * weights[source].get(row.id, 1.0)
            for row in rows
        )

    po_numbers = {_clean(row.purchasing_document) for row in pos} - {None}
    po_totals = {
        "ordered_quantity": total("mt_poamount", pos, "order_quantity"),
        "delivered_quantity": total("mt_poamount", pos, "delivered_qty"),
        "pending_quantity": total("mt_poamount", pos, "still_to_deliver_qty"),
        "order_value": total("mt_poamount", pos, "net_order_value_inr"),
        "pending_value": total("mt_poamount", pos, "still_to_deliver_inr"),
        "delivered_value_inr_cr": total("mt_poamount", pos, "delivered_value_inr_cr"),
    }
    inventory_totals = {
        "quantity": total("mt_inventory", inventory, "quantity_inv"),
        "value": total("mt_inventory", inventory, "value_unrestricted"),
    }
    logistics_totals = {
        "purchase_order_count": len(po_numbers) * max(
            weights["mt_poamount"].values(), default=1.0
        ),
        "ordered_mw": total("mt_poamount", pos, "po_quantities_mw"),
        "inventory_item_count": sum(
            weights["mt_inventory"].get(row.id, 1.0) for row in inventory
        ),
        "inventory_mw": total("mt_inventory", inventory, "quantity_mw"),
        "in_transit_count": sum(
            weights["mt_poamount"].get(row.id, 1.0)
            for row in pos
            if _number(row.still_to_deliver_qty) > 0
        ),
        "in_transit_mw": sum(
            _number(row.still_to_deliver_qty)
            * _number(row.mw_multiplication_factor)
            * weights["mt_poamount"].get(row.id, 1.0)
            for row in pos
        ),
    }
    vendors_by_key: dict[str, dict] = {}
    for row in pos:
        name = _clean(row.vendor_name) or "Unknown"
        code = _clean(row.vendor_code)
        key = code or name.casefold()
        vendor = vendors_by_key.setdefault(
            key, {"vendor_code": code, "name": name, "order_value": 0.0}
        )
        value = row.net_order_value_inr
        if value is None:
            value = row.net_order_value
        vendor["order_value"] += (
            _number(value) * weights["mt_poamount"].get(row.id, 1.0)
        )
    vendors = sorted(
        vendors_by_key.values(),
        key=lambda vendor: (-vendor["order_value"], vendor["name"].casefold()),
    )
    issued = [row for row in documents if _clean(row.movement_type) in _ISSUE_MOVEMENTS]
    reversals = [row for row in documents if _clean(row.movement_type) in _REVERSAL_MOVEMENTS]
    issued_quantity = total("mt_materialdocument", issued, "quantity", absolute=True)
    reversal_quantity = total("mt_materialdocument", reversals, "quantity", absolute=True)
    issued_value = total("mt_materialdocument", issued, "amount_in_lc", absolute=True)
    reversal_value = total("mt_materialdocument", reversals, "amount_in_lc", absolute=True)
    consumption_totals = {
        "issued_quantity": issued_quantity, "reversal_quantity": reversal_quantity,
        "net_quantity": issued_quantity - reversal_quantity,
        "issued_value": issued_value, "reversal_value": reversal_value,
        "net_value": issued_value - reversal_value,
    }
    units, warnings = _unit_metadata(pos, inventory, documents)
    primary_scope = source_scopes["mt_poamount"]
    scope = {
        **primary_scope,
        "match_method": primary_scope["type"],
        "project_capacity_mwac": max((_number(item.capacity_mwac) for item in mappings), default=0.0),
        "wbs_is_authoritative": primary_scope["type"] == "wbs",
        "sources": source_scopes,
    }
    records = {"purchase_orders": pos, "inventory": inventory, "material_documents": documents}
    return {
        "project_id": project_id, "project_name": project_name, "has_data": any(records.values()),
        "scope": scope,
        "counts": {
            "po_row_count": len(pos), "distinct_po_count": len(po_numbers),
            "inventory_row_count": len(inventory), "material_document_row_count": len(documents),
        },
        "totals": {
            "purchase_orders": po_totals,
            "inventory": inventory_totals,
            "logistics": logistics_totals,
            "consumption": consumption_totals,
        },
        "vendors": vendors,
        "units": units, "warnings": warnings,
        "freshness": {source: _freshness(selected[source]) for source in _SOURCES},
        "records": records, **records,
        "record_allocations": weights,
    }


def get_sap_projects_data(db: Session, project_ids: Iterable[str], mappings: Iterable | None = None) -> dict[str, dict]:
    snapshot = build_sap_snapshot(db, mappings)
    results = {
        project_id: get_sap_project_data(db, project_id, snapshot)
        for project_id in dict.fromkeys(project_ids)
    }
    for mapping in snapshot.mappings:
        if not mapping.project_id:
            results[f"mapping:{mapping.id}"] = get_sap_project_data(
                db, None, snapshot, mapping_id=mapping.id
            )
    return results


def _empty_result(project_id: str, project_name: str) -> dict:
    empty_totals = {
        "purchase_orders": {"ordered_quantity": 0.0, "delivered_quantity": 0.0, "pending_quantity": 0.0, "order_value": 0.0, "pending_value": 0.0, "delivered_value_inr_cr": 0.0},
        "inventory": {"quantity": 0.0, "value": 0.0},
        "logistics": {"purchase_order_count": 0.0, "ordered_mw": 0.0, "inventory_item_count": 0.0, "inventory_mw": 0.0, "in_transit_count": 0.0, "in_transit_mw": 0.0},
        "consumption": {"issued_quantity": 0.0, "reversal_quantity": 0.0, "net_quantity": 0.0, "issued_value": 0.0, "reversal_value": 0.0, "net_value": 0.0},
    }
    source_scope = {"type": "unmapped", "wbs": None, "wbs_roots": [], "selected_plant": None, "plant_source": None, "allocation_ratio": 1.0, "shared_plant_capacity_mwac": None}
    return {
        "project_id": project_id, "project_name": project_name, "has_data": False,
        "scope": {**source_scope, "match_method": "unmapped", "project_capacity_mwac": 0.0, "wbs_is_authoritative": False, "sources": {name: dict(source_scope) for name in _SOURCES}},
        "counts": {"po_row_count": 0, "distinct_po_count": 0, "inventory_row_count": 0, "material_document_row_count": 0},
        "totals": empty_totals,
        "units": {"po_quantity_units": [], "po_value_currencies": [], "inventory_quantity_units": [], "material_document_quantity_units": [], "inventory_value_currency": None, "material_document_value_currency": None},
        "warnings": [], "freshness": {name: None for name in _SOURCES}, "vendors": [],
        "records": {"purchase_orders": [], "inventory": [], "material_documents": []},
        "purchase_orders": [], "inventory": [], "material_documents": [],
        "record_allocations": {name: {} for name in _SOURCES},
    }


load_sap_project_data = get_sap_project_data
get_project_sap_data = get_sap_project_data


class SapProjectDataService:
    get_by_project_id = staticmethod(get_sap_project_data)
    get_by_project_ids = staticmethod(get_sap_projects_data)
    snapshot = staticmethod(build_sap_snapshot)


SAPProjectDataService = SapProjectDataService
