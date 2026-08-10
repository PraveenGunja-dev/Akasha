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


def sap_get_po_summary(db: Session, project_id: str = None) -> dict:
    """Get purchase order summary: total ordered, delivered, pending, value.
    
    Use when: user asks about procurement status, PO progress, material delivery.
    """
    if not project_id or str(project_id).lower() in ('all', 'portfolio', 'none', 'nan', ''):
        pos = db.query(models.MTPOAmount).all()
        project_name = "Entire Portfolio / Khavda"
    else:
        sap_filter = _resolve_sap_filter(db, project_id)
        project_name = sap_filter["project_name"]
        pos = _query_po_by_project(db, sap_filter)
    
    if not pos:
        return {"project_id": project_id, "project_name": project_name, "has_data": False, "summary": {}}
    
    total_ordered = sum(_safe_int(po.order_quantity) for po in pos)
    total_delivered = sum(_safe_int(po.delivered_qty) for po in pos)
    total_pending = sum(_safe_int(po.still_to_deliver_qty) for po in pos)
    total_value_inr = sum(po.net_order_value_inr or 0 for po in pos)
    
    latest_upload = max((po.upload_time for po in pos if po.upload_time), default=None)
    
    return {
        "project_id": project_id or "ALL",
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


def sap_get_material_gaps(db: Session, project_id: str = None, limit: int = 15) -> list[dict]:
    """Get materials with pending deliveries, sorted by gap severity.
    
    Use when: user asks about material shortages, supply gaps, pending deliveries.
    """
    if not project_id or str(project_id).lower() in ('all', 'portfolio', 'none', 'nan', ''):
        pos = db.query(models.MTPOAmount).filter(models.MTPOAmount.still_to_deliver_qty > 0).all()
        p_name = "Entire Portfolio"
    else:
        sap_filter = _resolve_sap_filter(db, project_id)
        pos = _query_po_by_project(db, sap_filter)
        p_name = sap_filter["project_name"]
    
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
                "project_name": p_name,
                "_source_table": "mt_poamount",
            })
    
    gaps.sort(key=lambda x: x["pending"], reverse=True)
    return gaps[:limit]


def sap_get_vendor_performance(db: Session, project_id: str = None) -> list[dict]:
    """Get vendor delivery performance.
    
    Use when: user asks about vendor risk, vendor performance, supplier delays.
    """
    if not project_id or str(project_id).lower() in ('all', 'portfolio', 'none', 'nan', ''):
        pos = db.query(models.MTPOAmount).all()
        p_name = "Entire Portfolio"
    else:
        sap_filter = _resolve_sap_filter(db, project_id)
        pos = _query_po_by_project(db, sap_filter)
        p_name = sap_filter["project_name"]
    
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
                "project_name": p_name,
                "_source_table": "mt_poamount",
            })
    
    result.sort(key=lambda x: x["total_pending"], reverse=True)
    return result


def sap_get_inventory(db: Session, project_id: str = None) -> dict:
    """Get current inventory (MB52) for a project or entire portfolio.
    
    Use when: user asks about stock on hand, inventory levels, available materials.
    """
    if not project_id or str(project_id).lower() in ('all', 'portfolio', 'none', 'nan', ''):
        inv_records = db.query(models.MTInventory).filter(models.MTInventory.quantity_inv > 0).all()
        project_name = "Entire Portfolio / Khavda"
    else:
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
        return {"project_id": project_id or "ALL", "project_name": project_name, "has_data": False}
    
    total_qty = sum(_safe_int(r.quantity_inv) for r in inv_records)
    total_value = sum(r.value_unrestricted or 0 for r in inv_records)
    latest_upload = max((r.upload_time for r in inv_records if r.upload_time), default=None)
    
    return {
        "project_id": project_id or "ALL",
        "project_name": project_name,
        "has_data": True,
        "total_items": len(inv_records),
        "total_quantity": total_qty,
        "total_value_inr": round(total_value, 2),
        "_source_table": "mt_inventory",
        "_synced_at": latest_upload.isoformat() if latest_upload else None,
    }


def sap_get_consumption(db: Session, project_id: str = None) -> dict:
    """Get material consumption (MB51) data for a project or portfolio.
    
    Use when: user asks about material usage, consumption rates, issued quantities.
    """
    if not project_id or str(project_id).lower() in ('all', 'portfolio', 'none', 'nan', ''):
        records = db.query(models.MTMaterialDocument).all()
        project_name = "Entire Portfolio / Khavda"
    else:
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
        return {"project_id": project_id or "ALL", "project_name": project_name, "has_data": False}
    
    issued_qty = 0
    returned_qty = 0
    for r in records:
        mvt = str(r.movement_type).strip() if r.movement_type else ""
        qty = abs(_safe_int(r.quantity))
        if mvt in ("222", "262"):
            returned_qty += qty
        else:
            issued_qty += qty
    
    return {
        "project_id": project_id or "ALL",
        "project_name": project_name,
        "has_data": True,
        "total_records": len(records),
        "issued_qty": issued_qty,
        "returned_qty": returned_qty,
        "net_consumed": issued_qty - returned_qty,
        "_source_table": "mt_materialdocument",
    }


def sap_search_inventory(db: Session, query: str = None, plant_code: str = None, limit: int = 20) -> list[dict]:
    """Search live SAP inventory (MB52) by material description, material code, or plant code.
    
    Use when: user asks about specific stock items, e.g. 'how many cables do we have?', 'search scrap in inventory', 'stock at plant 6061'.
    """
    q = db.query(models.MTInventory)
    if plant_code:
        q = q.filter(models.MTInventory.plant_code == str(plant_code).strip())
    if query:
        term = f"%{query.strip()}%"
        q = q.filter(
            (models.MTInventory.material_name.ilike(term)) |
            (models.MTInventory.material_description.ilike(term)) |
            (models.MTInventory.material_code.ilike(term))
        )
    
    results = q.order_by(models.MTInventory.unrestricted_qty.desc()).limit(limit).all()
    
    items = []
    for r in results:
        items.append({
            "material_code": r.material_code,
            "material_name": r.material_name or r.material_description,
            "material_description": r.material_description,
            "plant_code": r.plant_code,
            "storage_location": r.storage_location_mapping,
            "wbs_element": r.wbs_element,
            "unrestricted_qty": r.unrestricted_qty or r.quantity_inv or 0,
            "base_unit": r.base_unit or "Units",
            "value_unrestricted_inr": r.value_unrestricted or 0,
            "_source_table": "mt_inventory"
        })
    return items


def sap_search_pos(db: Session, query: str = None, vendor_name: str = None, po_number: str = None, plant_code: str = None, limit: int = 20) -> list[dict]:
    """Search SAP Purchase Orders (ME2J) by PO number, vendor name, material text, buyer, or plant code.
    
    Use when: user asks about specific purchase orders, vendor orders, or buyer PO lists, e.g. 'show POs for Junjar Construction', 'find PO 5710005200'.
    """
    q = db.query(models.MTPOAmount)
    if po_number:
        q = q.filter(models.MTPOAmount.purchasing_document.ilike(f"%{po_number.strip()}%"))
    if vendor_name:
        q = q.filter(models.MTPOAmount.vendor_name.ilike(f"%{vendor_name.strip()}%"))
    if plant_code:
        q = q.filter(models.MTPOAmount.plant_code == str(plant_code).strip())
    if query:
        term = f"%{query.strip()}%"
        q = q.filter(
            (models.MTPOAmount.purchasing_document.ilike(term)) |
            (models.MTPOAmount.vendor_name.ilike(term)) |
            (models.MTPOAmount.short_text.ilike(term)) |
            (models.MTPOAmount.material_name.ilike(term)) |
            (models.MTPOAmount.buyer_name.ilike(term)) |
            (models.MTPOAmount.wbs_element.ilike(term))
        )
    
    results = q.order_by(models.MTPOAmount.id.desc()).limit(limit).all()
    
    items = []
    for r in results:
        items.append({
            "po_number": r.purchasing_document,
            "vendor_name": r.vendor_name,
            "material_name": r.short_text or r.material_name,
            "plant_code": r.plant_code,
            "wbs_element": r.wbs_element,
            "ordered_qty": r.order_quantity or 0,
            "delivered_qty": r.delivered_qty or 0,
            "pending_qty": r.still_to_deliver_qty or 0,
            "net_order_value_inr": r.net_order_value_inr or r.net_order_value or 0,
            "still_to_deliver_inr": r.still_to_deliver_inr or 0,
            "currency": r.currency or "INR",
            "buyer_name": r.buyer_name,
            "delivery_completed": r.delivery_completed_flag,
            "document_date": r.document_date.strftime("%Y-%m-%d") if r.document_date else None,
            "_source_table": "mt_poamount"
        })
    return items


def sap_search_consumption(db: Session, query: str = None, movement_type: str = None, plant_code: str = None, limit: int = 20) -> list[dict]:
    """Search SAP Material Consumption logs (MB51) by material description/code, movement type (221, 222, 261, 262), or plant.
    
    Use when: user asks about material movement or consumption logs, e.g. 'show movement 221 entries', 'consumption of sleeves'.
    """
    q = db.query(models.MTMaterialDocument)
    if movement_type:
        q = q.filter(models.MTMaterialDocument.movement_type == str(movement_type).strip())
    if plant_code:
        q = q.filter(models.MTMaterialDocument.plant_code == str(plant_code).strip())
    if query:
        term = f"%{query.strip()}%"
        q = q.filter(
            (models.MTMaterialDocument.material_name.ilike(term)) |
            (models.MTMaterialDocument.material_description.ilike(term)) |
            (models.MTMaterialDocument.material_code.ilike(term)) |
            (models.MTMaterialDocument.material_document.ilike(term)) |
            (models.MTMaterialDocument.wbs_element.ilike(term))
        )
    
    results = q.order_by(models.MTMaterialDocument.id.desc()).limit(limit).all()
    
    items = []
    for r in results:
        items.append({
            "material_document": r.material_document,
            "material_code": r.material_code,
            "material_name": r.material_name or r.material_description,
            "movement_type": r.movement_type,
            "quantity": r.quantity or 0,
            "base_unit": r.base_unit or "Units",
            "amount_in_lc": r.amount_in_lc or 0,
            "plant_code": r.plant_code,
            "storage_location": r.storage_location,
            "wbs_element": r.wbs_element,
            "posting_date": r.posting_date.strftime("%Y-%m-%d") if r.posting_date else None,
            "_source_table": "mt_materialdocument"
        })
    return items


def sap_get_portfolio_summary(db: Session) -> dict:
    """Get macro summary across all ingested SAP datasets (ME2J, MB52, MB51, Master Mapping).
    
    Use when: user asks for overall SAP status, total PO value across Khavda, or summary of SAP datasets.
    """
    po_count = db.query(models.MTPOAmount).count()
    po_total_value = db.query(func.sum(models.MTPOAmount.net_order_value_inr)).scalar() or 0.0
    
    inv_count = db.query(models.MTInventory).count()
    inv_total_value = db.query(func.sum(models.MTInventory.value_unrestricted)).scalar() or 0.0
    
    consumption_count = db.query(models.MTMaterialDocument).count()
    mapping_count = db.query(models.ProjectMapping).count()
    
    return {
        "master_project_mappings_count": mapping_count,
        "purchase_orders_me2j": {
            "total_records": po_count,
            "total_value_inr": round(po_total_value, 2),
            "total_value_cr": round(po_total_value / 10000000.0, 2)
        },
        "live_inventory_mb52": {
            "total_records": inv_count,
            "total_unrestricted_value_inr": round(inv_total_value, 2),
            "total_value_cr": round(inv_total_value / 10000000.0, 2)
        },
        "consumption_documents_mb51": {
            "total_records": consumption_count
        }
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


