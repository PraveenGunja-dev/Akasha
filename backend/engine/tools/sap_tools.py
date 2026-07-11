"""
Akasha Tools Layer — SAP Procurement/Supply Chain Tools

MCP-style tool functions for deterministic, read-only access to SAP data.
Covers: Purchase Orders (ME2J), Material Consumption (MB51), Inventory (MB52).
"""

import logging
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)


def _resolve_wbs(db: Session, project_id: str) -> str | None:
    """Resolve project_id to SAP WBS element via project_mapping."""
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()
    if not mapping:
        return None
    wbs = mapping.module_wbs
    if wbs and str(wbs).strip().lower() not in ('nan', 'none', 'null', ''):
        return str(wbs).strip()
    return None


def sap_get_po_summary(db: Session, project_id: str) -> dict:
    """Get purchase order summary: total ordered, delivered, pending, value.
    
    Use when: user asks about procurement status, PO progress, material delivery.
    """
    wbs = _resolve_wbs(db, project_id)
    if not wbs:
        return {"project_id": project_id, "has_data": False, "summary": {}}
    
    pos = db.query(models.MTPOAmount).filter(
        models.MTPOAmount.wbs_element.ilike(f"%{wbs}%")
    ).all()
    
    if not pos:
        return {"project_id": project_id, "has_data": False, "summary": {}}
    
    total_ordered = sum(po.order_quantity or 0 for po in pos)
    total_delivered = sum(po.delivered_qty or 0 for po in pos)
    total_pending = sum(po.still_to_deliver_qty or 0 for po in pos)
    total_value_inr = sum(po.net_order_value_inr or 0 for po in pos)
    
    # Find latest upload time for freshness
    latest_upload = max((po.upload_time for po in pos if po.upload_time), default=None)
    
    return {
        "project_id": project_id,
        "has_data": True,
        "summary": {
            "total_po_count": len(pos),
            "total_ordered_qty": total_ordered,
            "total_delivered_qty": total_delivered,
            "total_pending_qty": total_pending,
            "fulfillment_pct": round(total_delivered / total_ordered * 100, 1) if total_ordered > 0 else 0,
            "total_value_inr": total_value_inr,
        },
        "_source_table": "mt_poamount",
        "_synced_at": latest_upload.isoformat() if latest_upload else None,
    }


def sap_get_material_gaps(db: Session, project_id: str, limit: int = 15) -> list[dict]:
    """Get materials with pending deliveries, sorted by gap severity.
    
    Use when: user asks about material shortages, supply gaps, pending deliveries.
    """
    wbs = _resolve_wbs(db, project_id)
    if not wbs:
        return []
    
    pos = db.query(models.MTPOAmount).filter(
        models.MTPOAmount.wbs_element.ilike(f"%{wbs}%")
    ).all()
    
    material_agg = defaultdict(lambda: {"ordered": 0, "delivered": 0, "pending": 0, "name": ""})
    
    for po in pos:
        mat_key = po.material_name or po.material_code or "Unknown"
        material_agg[mat_key]["ordered"] += (po.order_quantity or 0)
        material_agg[mat_key]["delivered"] += (po.delivered_qty or 0)
        material_agg[mat_key]["pending"] += (po.still_to_deliver_qty or 0)
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
                "_source_table": "mt_poamount",
            })
    
    gaps.sort(key=lambda x: x["pending"], reverse=True)
    return gaps[:limit]


def sap_get_vendor_performance(db: Session, project_id: str) -> list[dict]:
    """Get vendor delivery performance for a project.
    
    Use when: user asks about vendor risk, vendor performance, supplier delays.
    """
    wbs = _resolve_wbs(db, project_id)
    if not wbs:
        return []
    
    pos = db.query(models.MTPOAmount).filter(
        models.MTPOAmount.wbs_element.ilike(f"%{wbs}%")
    ).all()
    
    vendor_agg = defaultdict(lambda: {"ordered": 0, "delivered": 0, "pending": 0, "po_count": 0})
    
    for po in pos:
        vendor = po.vendor_name or "Unknown"
        vendor_agg[vendor]["ordered"] += (po.order_quantity or 0)
        vendor_agg[vendor]["delivered"] += (po.delivered_qty or 0)
        vendor_agg[vendor]["pending"] += (po.still_to_deliver_qty or 0)
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
                "_source_table": "mt_poamount",
            })
    
    result.sort(key=lambda x: x["total_pending"], reverse=True)
    return result


def sap_get_inventory(db: Session, project_id: str) -> dict:
    """Get current inventory (MB52) for a project.
    
    Use when: user asks about stock on hand, inventory levels, available materials.
    """
    wbs = _resolve_wbs(db, project_id)
    if not wbs:
        return {"project_id": project_id, "has_data": False}
    
    inv_records = db.query(models.MTInventory).filter(
        models.MTInventory.wbs_element.ilike(f"%{wbs}%"),
        models.MTInventory.quantity_inv > 0
    ).all()
    
    if not inv_records:
        return {"project_id": project_id, "has_data": False}
    
    total_qty = sum(r.quantity_inv or 0 for r in inv_records)
    total_value = sum(r.value_unrestricted or 0 for r in inv_records)
    latest_upload = max((r.upload_time for r in inv_records if r.upload_time), default=None)
    
    return {
        "project_id": project_id,
        "has_data": True,
        "total_items": len(inv_records),
        "total_quantity": total_qty,
        "total_value_inr": total_value,
        "_source_table": "mt_inventory",
        "_synced_at": latest_upload.isoformat() if latest_upload else None,
    }


def sap_get_consumption(db: Session, project_id: str) -> dict:
    """Get material consumption (MB51) data for a project.
    
    Use when: user asks about material usage, consumption rates, issued quantities.
    """
    wbs = _resolve_wbs(db, project_id)
    if not wbs:
        return {"project_id": project_id, "has_data": False}
    
    records = db.query(models.MTMaterialDocument).filter(
        models.MTMaterialDocument.wbs_element.ilike(f"%{wbs}%")
    ).all()
    
    if not records:
        return {"project_id": project_id, "has_data": False}
    
    issued_qty = 0
    returned_qty = 0
    for r in records:
        mvt = str(r.movement_type).strip() if r.movement_type else ""
        qty = abs(r.quantity or 0)
        if mvt == "222":
            returned_qty += qty
        else:
            issued_qty += qty
    
    return {
        "project_id": project_id,
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
    wbs = _resolve_wbs(db, project_id)
    if not wbs:
        return {"project_id": project_id, "synced_at": None, "exists": False}
    
    latest = db.query(func.max(models.MTPOAmount.upload_time)).filter(
        models.MTPOAmount.wbs_element.ilike(f"%{wbs}%")
    ).scalar()
    
    return {
        "project_id": project_id,
        "synced_at": latest.isoformat() if latest else None,
        "exists": latest is not None,
    }
