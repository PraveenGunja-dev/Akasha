"""Thin chatbot adapters over the shared SAP project data service."""

from collections import defaultdict

from sqlalchemy.orm import Session

from services.sap_project_data_service import get_sap_project_data, wbs_membership


def _final_quantity(value):
    """Preserve legacy integer fields while rounding only after aggregation."""
    return int(round(float(value or 0)))


def _metadata(data: dict) -> dict:
    return {
        "scope": data["scope"],
        "counts": data["counts"],
        "units": data["units"],
        "warnings": data["warnings"],
        "freshness": data["freshness"],
    }


def _resolve_sap_filter(db: Session, project_id: str) -> dict:
    """Compatibility helper retained for KPI consumers."""
    data = get_sap_project_data(db, project_id)
    return {
        "wbs": data["scope"]["wbs"],
        "plant_code": data["scope"]["selected_plant"],
        "project_name": data["project_name"],
        "project_id": project_id,
    }


def _wbs_membership(column, root: str):
    return wbs_membership(column, root)


def _query_po_by_project(db: Session, sap_filter: dict):
    project_id = sap_filter.get("project_id")
    if project_id:
        return get_sap_project_data(db, project_id)["purchase_orders"]
    # Older callers may pass a manually constructed filter.
    import models
    if sap_filter.get("wbs"):
        return db.query(models.MTPOAmount).filter(
            wbs_membership(models.MTPOAmount.wbs_element, sap_filter["wbs"])
        ).all()
    if sap_filter.get("plant_code"):
        return db.query(models.MTPOAmount).filter(
            models.MTPOAmount.plant_code == sap_filter["plant_code"]
        ).all()
    return []


def sap_get_source_records(db: Session, project_id: str, source_entity: str) -> list:
    data = get_sap_project_data(db, project_id)
    return {
        "mt_poamount": data["purchase_orders"],
        "mt_inventory": data["inventory"],
        "mt_materialdocument": data["material_documents"],
    }.get(source_entity, [])


def sap_get_po_summary(db: Session, project_id: str) -> dict:
    data = get_sap_project_data(db, project_id)
    totals = data["totals"]["purchase_orders"]
    result = {
        "project_id": project_id,
        "project_name": data["project_name"],
        "has_data": bool(data["purchase_orders"]),
        "summary": {},
        **_metadata(data),
    }
    if not data["purchase_orders"]:
        return result
    ordered = totals["ordered_quantity"]
    result.update({
        "summary": {
            "total_po_count": data["counts"]["po_row_count"],
            "po_row_count": data["counts"]["po_row_count"],
            "distinct_po_count": data["counts"]["distinct_po_count"],
            "total_ordered_qty": _final_quantity(ordered),
            "total_ordered_qty_raw": ordered,
            "total_delivered_qty": _final_quantity(totals["delivered_quantity"]),
            "total_delivered_qty_raw": totals["delivered_quantity"],
            "total_pending_qty": _final_quantity(totals["pending_quantity"]),
            "total_pending_qty_raw": totals["pending_quantity"],
            "fulfillment_pct": round(totals["delivered_quantity"] / ordered * 100, 1) if ordered > 0 else 0,
            "total_value_inr": round(totals["order_value"], 2),
            "currency": data["units"]["po_value_currencies"],
            "quantity_units": data["units"]["po_quantity_units"],
        },
        "_source_table": "mt_poamount",
        "_synced_at": data["freshness"]["mt_poamount"],
    })
    return result


def sap_get_material_gaps(db: Session, project_id: str, limit: int = 15) -> list[dict]:
    data = get_sap_project_data(db, project_id)
    ratio = data["scope"]["allocation_ratio"]
    aggregates = defaultdict(lambda: {"ordered": 0.0, "delivered": 0.0, "pending": 0.0})
    for po in data["purchase_orders"]:
        material = po.material_name or po.material_code or "Unknown"
        aggregates[material]["ordered"] += float(po.order_quantity or 0) * ratio
        aggregates[material]["delivered"] += float(po.delivered_qty or 0) * ratio
        aggregates[material]["pending"] += float(po.still_to_deliver_qty or 0) * ratio
    result = []
    for material, aggregate in aggregates.items():
        if aggregate["pending"] > 0:
            result.append({
                "material": material,
                "ordered": _final_quantity(aggregate["ordered"]),
                "delivered": _final_quantity(aggregate["delivered"]),
                "pending": _final_quantity(aggregate["pending"]),
                "gap_pct": round(aggregate["pending"] / aggregate["ordered"] * 100, 1) if aggregate["ordered"] > 0 else 0,
                "project_name": data["project_name"],
                "quantity_units": data["units"]["po_quantity_units"],
                "scope": data["scope"],
                "freshness": data["freshness"]["mt_poamount"],
                "warnings": data["warnings"],
                "_source_table": "mt_poamount",
            })
    result.sort(key=lambda row: (-row["pending"], str(row["material"])))
    return result[:limit]


def sap_get_vendor_performance(db: Session, project_id: str) -> list[dict]:
    data = get_sap_project_data(db, project_id)
    ratio = data["scope"]["allocation_ratio"]
    aggregates = defaultdict(lambda: {
        "ordered": 0.0, "delivered": 0.0, "pending": 0.0,
        "rows": 0, "po_numbers": set(),
    })
    for po in data["purchase_orders"]:
        aggregate = aggregates[po.vendor_name or "Unknown"]
        aggregate["ordered"] += float(po.order_quantity or 0) * ratio
        aggregate["delivered"] += float(po.delivered_qty or 0) * ratio
        aggregate["pending"] += float(po.still_to_deliver_qty or 0) * ratio
        aggregate["rows"] += 1
        if po.purchasing_document:
            aggregate["po_numbers"].add(str(po.purchasing_document).strip())
    result = []
    for vendor, aggregate in aggregates.items():
        if aggregate["ordered"] > 0:
            result.append({
                "vendor": vendor,
                "total_ordered": _final_quantity(aggregate["ordered"]),
                "total_delivered": _final_quantity(aggregate["delivered"]),
                "total_pending": _final_quantity(aggregate["pending"]),
                "po_count": aggregate["rows"],
                "po_row_count": aggregate["rows"],
                "distinct_po_count": len(aggregate["po_numbers"]),
                "fulfillment_pct": round((aggregate["ordered"] - aggregate["pending"]) / aggregate["ordered"] * 100, 1),
                "project_name": data["project_name"],
                "quantity_units": data["units"]["po_quantity_units"],
                "scope": data["scope"],
                "freshness": data["freshness"]["mt_poamount"],
                "warnings": data["warnings"],
                "_source_table": "mt_poamount",
            })
    result.sort(key=lambda row: (-row["total_pending"], str(row["vendor"])))
    return result


def sap_get_inventory(db: Session, project_id: str) -> dict:
    data = get_sap_project_data(db, project_id)
    totals = data["totals"]["inventory"]
    result = {
        "project_id": project_id,
        "project_name": data["project_name"],
        "has_data": bool(data["inventory"]),
        **_metadata(data),
    }
    if not data["inventory"]:
        return result
    result.update({
        "total_items": data["counts"]["inventory_row_count"],
        "inventory_row_count": data["counts"]["inventory_row_count"],
        "total_quantity": _final_quantity(totals["quantity"]),
        "total_quantity_raw": totals["quantity"],
        "total_value_inr": round(totals["value"], 2),
        "quantity_units": data["units"]["inventory_quantity_units"],
        "value_currency": data["units"]["inventory_value_currency"],
        "_source_table": "mt_inventory",
        "_synced_at": data["freshness"]["mt_inventory"],
    })
    return result


def sap_get_consumption(db: Session, project_id: str) -> dict:
    data = get_sap_project_data(db, project_id)
    totals = data["totals"]["consumption"]
    result = {
        "project_id": project_id,
        "project_name": data["project_name"],
        "has_data": bool(data["material_documents"]),
        **_metadata(data),
    }
    if not data["material_documents"]:
        return result
    result.update({
        "total_records": data["counts"]["material_document_row_count"],
        "material_document_row_count": data["counts"]["material_document_row_count"],
        "issued_qty": _final_quantity(totals["issued_quantity"]),
        "returned_qty": _final_quantity(totals["reversal_quantity"]),
        "net_consumed": _final_quantity(totals["net_quantity"]),
        "quantity_units": data["units"]["material_document_quantity_units"],
        "value_currency": data["units"]["material_document_value_currency"],
        "_source_table": "mt_materialdocument",
        "_synced_at": data["freshness"]["mt_materialdocument"],
    })
    return result


def sap_get_freshness(db: Session, project_id: str) -> dict:
    data = get_sap_project_data(db, project_id)
    latest = max((value for value in data["freshness"].values() if value), default=None)
    return {
        "project_id": project_id,
        "project_name": data["project_name"],
        "synced_at": data["freshness"]["mt_poamount"],
        "exists": latest is not None,
        "freshness": data["freshness"],
        "scope": data["scope"],
    }
