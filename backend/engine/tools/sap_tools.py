"""
Akasha Tools Layer — SAP Procurement/Supply Chain Tools

MCP-style tool functions for deterministic, read-only access to SAP data.
Covers: Purchase Orders (ZSPS), Material Consumption (MB51), Inventory (MB52).
"""

import logging
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)


def _resolve_sap_filter(db: Session, project_id: str) -> dict:
    """Resolve project_id to SAP WBS element and/or plant_code via project_mapping.
    
    Returns dict with 'wbs', 'plant_code', and 'project_name' for display.
    Uses WBS as primary key, plant_code as fallback.
    """
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()
    if not mapping:
        return {"wbs": None, "plant_code": None, "project_name": project_id}
    
    project_name = mapping.project_name_from_p6 or mapping.project or project_id
    
    wbs = mapping.module_wbs
    if wbs and str(wbs).strip().lower() not in ('nan', 'none', 'null', ''):
        wbs = str(wbs).strip()
    else:
        wbs = None
    
    plant_code = mapping.spv_plant_code
    if plant_code and str(plant_code).strip().lower() not in ('nan', 'none', 'null', ''):
        plant_code = str(plant_code).strip()
    else:
        plant_code = None
    
    return {"wbs": wbs, "plant_code": plant_code, "project_name": project_name}


def _query_po_by_project(db: Session, sap_filter: dict):
    """Query MTPOAmount records using WBS (primary) or plant_code (fallback)."""
    wbs = sap_filter.get("wbs")
    plant_code = sap_filter.get("plant_code")
    
    if wbs:
        # Use prefix match (tighter than contains) to avoid cross-project contamination
        pos = db.query(models.MTPOAmount).filter(
            models.MTPOAmount.wbs_element.ilike(f"{wbs}%")
        ).all()
        if pos:
            return pos
    
    # Fallback: match by plant_code
    if plant_code:
        pos = db.query(models.MTPOAmount).filter(
            models.MTPOAmount.plant_code == plant_code
        ).all()
        if pos:
            return pos
    
    return []


def _safe_int(val) -> int:
    """Convert a float quantity to int safely. SAP quantities are whole units."""
    if val is None:
        return 0
    return int(round(float(val)))


def sap_get_po_summary(db: Session, project_id: str) -> dict:
    """Get purchase order summary: total ordered, delivered, pending, value.
    
    Use when: user asks about procurement status, PO progress, material delivery.
    """
    sap_filter = _resolve_sap_filter(db, project_id)
    project_name = sap_filter["project_name"]
    
    pos = _query_po_by_project(db, sap_filter)
    
    if not pos:
        return {"project_id": project_id, "project_name": project_name, "has_data": False, "summary": {}}
    
    total_ordered = sum(_safe_int(po.order_quantity) for po in pos)
    total_delivered = sum(_safe_int(po.delivered_qty) for po in pos)
    total_pending = sum(_safe_int(po.still_to_deliver_qty) for po in pos)
    total_value_inr = sum(po.net_order_value_inr or 0 for po in pos)
    
    # Find latest upload time for freshness
    latest_upload = max((po.upload_time for po in pos if po.upload_time), default=None)
    
    return {
        "project_id": project_id,
        "project_name": project_name,
        "has_data": True,
        "summary": {
            "total_po_count": len(pos),
            "total_ordered_qty": total_ordered,
            "total_delivered_qty": total_delivered,
            "total_pending_qty": total_pending,
            "fulfillment_pct": round(total_delivered / total_ordered * 100, 1) if total_ordered > 0 else 0,
            "total_value_inr": round(total_value_inr, 2),
        },
        "_source_table": "mt_poamount",
        "_synced_at": latest_upload.isoformat() if latest_upload else None,
    }


def sap_get_material_gaps(db: Session, project_id: str, limit: int = 15) -> list[dict]:
    """Get materials with pending deliveries, sorted by gap severity.
    
    Use when: user asks about material shortages, supply gaps, pending deliveries.
    """
    sap_filter = _resolve_sap_filter(db, project_id)
    pos = _query_po_by_project(db, sap_filter)
    
    if not pos:
        return []
    
    material_agg = defaultdict(lambda: {"ordered": 0, "delivered": 0, "pending": 0, "name": ""})
    
    for po in pos:
        mat_key = po.material_name or po.material_code or "Unknown"
        material_agg[mat_key]["ordered"] += _safe_int(po.order_quantity)
        material_agg[mat_key]["delivered"] += _safe_int(po.delivered_qty)
        material_agg[mat_key]["pending"] += _safe_int(po.still_to_deliver_qty)
        material_agg[mat_key]["name"] = mat_key
    
    gaps = []
    for mat_key, agg in material_agg.items():
        if agg["pending"] > 0:
            gaps.append({
                "material": mat_key,
                "ordered": agg["ordered"],
                "delivered": agg["delivered"],
                "pending": agg["pending"],
                "gap_pct": round(agg["pending"] / agg["ordered"] * 100, 1) if agg["ordered"] > 0 else 0,
                "project_name": sap_filter["project_name"],
                "_source_table": "mt_poamount",
            })
    
    gaps.sort(key=lambda x: x["pending"], reverse=True)
    return gaps[:limit]


def sap_get_vendor_performance(db: Session, project_id: str) -> list[dict]:
    """Get vendor delivery performance for a project.
    
    Use when: user asks about vendor risk, vendor performance, supplier delays.
    """
    sap_filter = _resolve_sap_filter(db, project_id)
    pos = _query_po_by_project(db, sap_filter)
    
    if not pos:
        return []
    
    vendor_agg = defaultdict(lambda: {"ordered": 0, "delivered": 0, "pending": 0, "po_count": 0})
    
    for po in pos:
        vendor = po.vendor_name or "Unknown"
        vendor_agg[vendor]["ordered"] += _safe_int(po.order_quantity)
        vendor_agg[vendor]["delivered"] += _safe_int(po.delivered_qty)
        vendor_agg[vendor]["pending"] += _safe_int(po.still_to_deliver_qty)
        vendor_agg[vendor]["po_count"] += 1
    
    result = []
    for vendor, agg in vendor_agg.items():
        if agg["ordered"] > 0:
            result.append({
                "vendor": vendor,
                "total_ordered": agg["ordered"],
                "total_delivered": agg["delivered"],
                "total_pending": agg["pending"],
                "po_count": agg["po_count"],
                "fulfillment_pct": round((agg["ordered"] - agg["pending"]) / agg["ordered"] * 100, 1) if agg["ordered"] > 0 else 0,
                "project_name": sap_filter["project_name"],
                "_source_table": "mt_poamount",
            })
    
    result.sort(key=lambda x: x["total_pending"], reverse=True)
    return result


def sap_get_inventory(db: Session, project_id: str) -> dict:
    """Get current inventory (MB52) for a project.
    
    Use when: user asks about stock on hand, inventory levels, available materials.
    """
    sap_filter = _resolve_sap_filter(db, project_id)
    project_name = sap_filter["project_name"]
    wbs = sap_filter.get("wbs")
    plant_code = sap_filter.get("plant_code")
    
    inv_records = []
    if wbs:
        inv_records = db.query(models.MTInventory).filter(
            models.MTInventory.wbs_element.ilike(f"{wbs}%"),
            models.MTInventory.quantity_inv > 0
        ).all()
    
    if not inv_records and plant_code:
        inv_records = db.query(models.MTInventory).filter(
            models.MTInventory.plant_code == plant_code,
            models.MTInventory.quantity_inv > 0
        ).all()
    
    if not inv_records:
        return {"project_id": project_id, "project_name": project_name, "has_data": False}
    
    total_qty = sum(_safe_int(r.quantity_inv) for r in inv_records)
    total_value = sum(r.value_unrestricted or 0 for r in inv_records)
    latest_upload = max((r.upload_time for r in inv_records if r.upload_time), default=None)
    
    return {
        "project_id": project_id,
        "project_name": project_name,
        "has_data": True,
        "total_items": len(inv_records),
        "total_quantity": total_qty,
        "total_value_inr": round(total_value, 2),
        "_source_table": "mt_inventory",
        "_synced_at": latest_upload.isoformat() if latest_upload else None,
    }


def sap_get_consumption(db: Session, project_id: str) -> dict:
    """Get material consumption (MB51) data for a project.
    
    Use when: user asks about material usage, consumption rates, issued quantities.
    """
    sap_filter = _resolve_sap_filter(db, project_id)
    project_name = sap_filter["project_name"]
    wbs = sap_filter.get("wbs")
    plant_code = sap_filter.get("plant_code")
    
    records = []
    if wbs:
        records = db.query(models.MTMaterialDocument).filter(
            models.MTMaterialDocument.wbs_element.ilike(f"{wbs}%")
        ).all()
    
    if not records and plant_code:
        records = db.query(models.MTMaterialDocument).filter(
            models.MTMaterialDocument.plant_code == plant_code
        ).all()
    
    if not records:
        return {"project_id": project_id, "project_name": project_name, "has_data": False}
    
    issued_qty = 0
    returned_qty = 0
    for r in records:
        mvt = str(r.movement_type).strip() if r.movement_type else ""
        qty = abs(_safe_int(r.quantity))
        if mvt == "222":
            returned_qty += qty
        else:
            issued_qty += qty
    
    return {
        "project_id": project_id,
        "project_name": project_name,
        "has_data": True,
        "total_records": len(records),
        "issued_qty": issued_qty,
        "returned_qty": returned_qty,
        "net_consumed": issued_qty - returned_qty,
        "_source_table": "mt_materialdocument",
    }


def sap_get_freshness(db: Session, project_id: str) -> dict:
    """Get the latest upload timestamp for SAP data of a project.
    
    Use when: determining if cached SAP data is still valid (Step 2 of pipeline).
    """
    sap_filter = _resolve_sap_filter(db, project_id)
    wbs = sap_filter.get("wbs")
    plant_code = sap_filter.get("plant_code")
    
    latest = None
    if wbs:
        latest = db.query(func.max(models.MTPOAmount.upload_time)).filter(
            models.MTPOAmount.wbs_element.ilike(f"{wbs}%")
        ).scalar()
    
    if not latest and plant_code:
        latest = db.query(func.max(models.MTPOAmount.upload_time)).filter(
            models.MTPOAmount.plant_code == plant_code
        ).scalar()
    
    return {
        "project_id": project_id,
        "project_name": sap_filter["project_name"],
        "synced_at": latest.isoformat() if latest else None,
        "exists": latest is not None,
    }

