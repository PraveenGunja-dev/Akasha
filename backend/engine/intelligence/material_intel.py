"""
Akasha Intelligence Engine — Material & Procurement Intelligence

Analyzes SAP PO/Inventory/Material data to produce:
- Material-to-activity dependency linking
- Vendor reliability scoring
- Material shortfall predictions
- PO expedite prioritization
- Procurement-specific insights and next steps

Read-only: never modifies existing data.
"""

import logging
from datetime import datetime
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

import models

logger = logging.getLogger(__name__)


def _query_pos(db: Session, ctx: dict):
    """Query PO data for a project using WBS or plant code."""
    wbs = ctx.get("wbs")
    plant_code = ctx.get("plant_code")

    if wbs:
        pos = db.query(models.MTPOAmount).filter(
            models.MTPOAmount.wbs_element.ilike(f"{wbs}%")
        ).all()
        if pos:
            return pos

    if plant_code:
        pos = db.query(models.MTPOAmount).filter(
            models.MTPOAmount.plant_code == plant_code
        ).all()
        if pos:
            return pos

    return []


def _query_inventory(db: Session, ctx: dict):
    """Query inventory data for a project."""
    wbs = ctx.get("wbs")
    plant_code = ctx.get("plant_code")

    if wbs:
        inv = db.query(models.MTInventory).filter(
            models.MTInventory.wbs_element.ilike(f"{wbs}%")
        ).all()
        if inv:
            return inv

    if plant_code:
        inv = db.query(models.MTInventory).filter(
            models.MTInventory.plant_code == plant_code
        ).all()
        if inv:
            return inv

    return []


def _query_consumption(db: Session, ctx: dict):
    """Query material consumption (MB51) data for a project."""
    wbs = ctx.get("wbs")
    plant_code = ctx.get("plant_code")

    if wbs:
        docs = db.query(models.MTMaterialDocument).filter(
            models.MTMaterialDocument.wbs_element.ilike(f"{wbs}%")
        ).all()
        if docs:
            return docs

    if plant_code:
        docs = db.query(models.MTMaterialDocument).filter(
            models.MTMaterialDocument.plant_code == plant_code
        ).all()
        if docs:
            return docs

    return []


def analyze_materials(db: Session, ctx: dict) -> dict:
    """Full material & procurement intelligence analysis."""
    project_name = ctx["project_name"]

    pos = _query_pos(db, ctx)
    inventory = _query_inventory(db, ctx)
    consumption = _query_consumption(db, ctx)

    if not pos and not inventory:
        return {
            "has_data": False,
            "health_score": None,
            "insights": [{
                "severity": "info",
                "domain": "material",
                "title": f"No SAP procurement data for {project_name}",
                "description": "No purchase orders or inventory data found for this project's WBS/plant code.",
                "impact": "Cannot assess material readiness",
            }],
            "next_steps": [],
        }

    now = datetime.utcnow()

    # ═══════════════════════════════════════════════════════
    # 1. PO ANALYSIS — Delivery tracking
    # ═══════════════════════════════════════════════════════
    total_pos = len(pos)
    total_ordered_qty = 0
    total_delivered_qty = 0
    total_pending_qty = 0
    total_po_value_inr = 0
    overdue_pos = []

    vendor_stats = defaultdict(lambda: {
        "total_pos": 0, "delivered": 0, "pending": 0,
        "overdue": 0, "total_value": 0, "materials": set(),
    })

    material_stats = defaultdict(lambda: {
        "ordered": 0, "delivered": 0, "pending": 0, "value": 0,
        "vendors": set(), "overdue": False,
    })

    for po in pos:
        ordered = float(po.order_quantity or po.po_quantities or 0)
        delivered = float(po.delivered_qty or po.quantity_received or 0)
        pending = float(po.still_to_deliver_qty or po.still_to_be_delivered_qty or 0)
        value = float(po.net_order_value_inr or po.net_order_value or 0)

        total_ordered_qty += ordered
        total_delivered_qty += delivered
        total_pending_qty += pending
        total_po_value_inr += value

        vendor = po.vendor_name or "Unknown Vendor"
        material = po.material_name or po.material_code or "Unknown Material"
        vs = vendor_stats[vendor]
        vs["total_pos"] += 1
        vs["total_value"] += value
        vs["materials"].add(material)

        ms = material_stats[material]
        ms["ordered"] += ordered
        ms["delivered"] += delivered
        ms["pending"] += pending
        ms["value"] += value
        ms["vendors"].add(vendor)

        if pending > 0:
            vs["pending"] += 1
            is_overdue = False

            # Check if delivery is overdue
            if po.delivery_date and po.delivery_date < now:
                is_overdue = True
                vs["overdue"] += 1
                ms["overdue"] = True
                overdue_pos.append({
                    "po_number": po.purchasing_document,
                    "vendor": vendor,
                    "material": material,
                    "pending_qty": round(pending, 1),
                    "value_inr": round(value, 2),
                    "delivery_date": po.delivery_date.isoformat() if po.delivery_date else None,
                    "days_overdue": (now - po.delivery_date).days if po.delivery_date else 0,
                })
        else:
            vs["delivered"] += 1

    # Sort overdue POs by days overdue
    overdue_pos.sort(key=lambda x: x.get("days_overdue", 0), reverse=True)

    fulfillment_pct = round(total_delivered_qty / max(total_ordered_qty, 1) * 100, 1)

    # ═══════════════════════════════════════════════════════
    # 2. VENDOR SCORECARD
    # ═══════════════════════════════════════════════════════
    vendor_scorecards = []
    for vendor, vs in vendor_stats.items():
        delivery_rate = round(vs["delivered"] / max(vs["total_pos"], 1) * 100, 1)
        vendor_scorecards.append({
            "vendor": vendor,
            "total_pos": vs["total_pos"],
            "delivered": vs["delivered"],
            "pending": vs["pending"],
            "overdue": vs["overdue"],
            "delivery_rate_pct": delivery_rate,
            "total_value_inr": round(vs["total_value"], 2),
            "total_value_cr": round(vs["total_value"] / 10000000, 2),
            "materials_count": len(vs["materials"]),
            "reliability": "GOOD" if delivery_rate >= 80 else "FAIR" if delivery_rate >= 50 else "POOR",
        })
    vendor_scorecards.sort(key=lambda x: x["delivery_rate_pct"])

    # ═══════════════════════════════════════════════════════
    # 3. MATERIAL GAPS (pending materials ranked by severity)
    # ═══════════════════════════════════════════════════════
    material_gaps = []
    for material, ms in material_stats.items():
        if ms["pending"] > 0:
            gap_pct = round(ms["pending"] / max(ms["ordered"], 1) * 100, 1)
            material_gaps.append({
                "material": material,
                "ordered": round(ms["ordered"], 1),
                "delivered": round(ms["delivered"], 1),
                "pending": round(ms["pending"], 1),
                "gap_pct": gap_pct,
                "is_overdue": ms["overdue"],
                "value_inr": round(ms["value"], 2),
                "vendor_count": len(ms["vendors"]),
            })
    material_gaps.sort(key=lambda x: x["gap_pct"], reverse=True)

    # ═══════════════════════════════════════════════════════
    # 4. INVENTORY ANALYSIS
    # ═══════════════════════════════════════════════════════
    total_inventory_qty = sum(float(inv.quantity_inv or 0) for inv in inventory)
    total_inventory_value = sum(float(inv.value_unrestricted or 0) for inv in inventory)

    # ═══════════════════════════════════════════════════════
    # 5. HEALTH SCORE
    # ═══════════════════════════════════════════════════════
    overdue_penalty = min(len(overdue_pos) * 5, 40)
    fulfillment_score = fulfillment_pct * 0.6  # Max 60 points
    health_score = round(max(0, min(100, fulfillment_score + 40 - overdue_penalty)), 1)

    # ═══════════════════════════════════════════════════════
    # 6. INSIGHTS
    # ═══════════════════════════════════════════════════════
    insights = []

    if overdue_pos:
        worst_po = overdue_pos[0]
        insights.append({
            "severity": "critical" if len(overdue_pos) > 5 else "high",
            "domain": "material",
            "title": f"{len(overdue_pos)} purchase orders are overdue",
            "description": f"Worst: PO {worst_po['po_number']} from {worst_po['vendor']} — "
                          f"{worst_po['days_overdue']} days overdue, {worst_po['material']}",
            "impact": f"Overdue materials may be blocking construction activities",
            "evidence": {"overdue_count": len(overdue_pos), "worst_po": worst_po},
        })

    if fulfillment_pct < 50:
        insights.append({
            "severity": "high",
            "domain": "material",
            "title": f"Only {fulfillment_pct}% of ordered materials delivered",
            "description": f"Ordered: {round(total_ordered_qty):,} units, Delivered: {round(total_delivered_qty):,}, "
                          f"Pending: {round(total_pending_qty):,}",
            "impact": "Low fulfillment may cause construction delays",
        })

    # Identify unreliable vendors
    poor_vendors = [v for v in vendor_scorecards if v["reliability"] == "POOR" and v["total_pos"] >= 3]
    if poor_vendors:
        insights.append({
            "severity": "high",
            "domain": "material",
            "title": f"{len(poor_vendors)} vendors have POOR delivery reliability",
            "description": f"Worst: {poor_vendors[0]['vendor']} — "
                          f"{poor_vendors[0]['delivery_rate_pct']}% on-time delivery across {poor_vendors[0]['total_pos']} POs",
            "impact": "Consider alternate sourcing or escalation",
        })

    # ═══════════════════════════════════════════════════════
    # 7. NEXT STEPS
    # ═══════════════════════════════════════════════════════
    next_steps = []

    if overdue_pos:
        next_steps.append({
            "priority": "P1",
            "category": "procurement",
            "action": f"Expedite top {min(3, len(overdue_pos))} overdue POs — "
                      f"{', '.join(p['po_number'] for p in overdue_pos[:3])}",
            "reason": f"{len(overdue_pos)} POs overdue, total pending value: "
                      f"₹{round(sum(p['value_inr'] for p in overdue_pos)/10000000, 2)} Cr",
            "assigned_role": "procurement_head",
        })

    if poor_vendors:
        next_steps.append({
            "priority": "P2",
            "category": "procurement",
            "action": f"Escalate vendor {poor_vendors[0]['vendor']} — "
                      f"{poor_vendors[0]['overdue']} overdue deliveries",
            "reason": f"Only {poor_vendors[0]['delivery_rate_pct']}% on-time delivery. "
                      f"Exposure: ₹{poor_vendors[0]['total_value_cr']} Cr",
            "assigned_role": "procurement_head",
        })

    if material_gaps and material_gaps[0]["gap_pct"] > 60:
        worst_gap = material_gaps[0]
        next_steps.append({
            "priority": "P1",
            "category": "procurement",
            "action": f"Arrange alternate source for {worst_gap['material']} — "
                      f"{worst_gap['gap_pct']}% undelivered",
            "reason": f"Only {round(worst_gap['delivered'])} of {round(worst_gap['ordered'])} units delivered",
            "assigned_role": "procurement_head",
        })

    return {
        "has_data": True,
        "health_score": health_score,

        # Summary
        "summary": {
            "total_pos": total_pos,
            "total_ordered_qty": round(total_ordered_qty, 1),
            "total_delivered_qty": round(total_delivered_qty, 1),
            "total_pending_qty": round(total_pending_qty, 1),
            "fulfillment_pct": fulfillment_pct,
            "total_po_value_cr": round(total_po_value_inr / 10000000, 2),
            "overdue_po_count": len(overdue_pos),
            "total_inventory_qty": round(total_inventory_qty, 1),
            "total_inventory_value_cr": round(total_inventory_value / 10000000, 2),
        },

        # Detailed breakdowns
        "overdue_pos": overdue_pos[:20],
        "vendor_scorecards": vendor_scorecards[:15],
        "material_gaps": material_gaps[:20],

        # Intelligence outputs
        "insights": insights,
        "next_steps": next_steps,
    }
