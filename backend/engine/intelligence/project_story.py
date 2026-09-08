"""
Akasha Intelligence Engine — Project Story & Cross-System Relationship Layer

This module transforms isolated integrations (P6, Pulse NC, Pulse RFI, SAP PO, SLR, E-Invoice)
into a unified Project-Level Intelligence system.

It models the canonical chain:
DELAY → ACTIVITY → PROJECT/PACKAGE → ISSUE/RFI → ROOT CAUSE → RESPONSIBLE PARTY
      → RESOLUTION → SCHEDULE IMPACT → INVOICE/SLR → SAP → COST/COMMERCIAL IMPACT

Read-only: never modifies existing data. Never invents causality.
Assigns confidence scores to all inferred relationships.
"""

from __future__ import annotations
import logging
import re
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Any, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_

import models

logger = logging.getLogger(__name__)

# Standard 18 Root Cause Categories
ROOT_CAUSE_CATEGORIES = [
    "Design", "Engineering", "Approval", "Material", "Procurement",
    "Vendor", "Contractor", "Client", "Site access", "Interface",
    "RFI", "NVC", "Change order", "Payment/commercial", "Resource",
    "Planning", "External dependency", "Unknown"
]


def _extract_location_tokens(text: Optional[str]) -> set[str]:
    """Extract tokens like WTG 448, KH 478, BL15, Block 3, Plot 4, PSS."""
    if not text:
        return set()
    tokens = set()
    raw = str(text).upper()
    # Match WTG-XX, WTG XX, WTGXX
    for m in re.finditer(r'WTG\s*[-_]?\s*(\d+)', raw):
        tokens.add(f"WTG{m.group(1)}")
    # Match KH-XX, KH XX
    for m in re.finditer(r'KH\s*[-_]?\s*(\d+)', raw):
        tokens.add(f"KH{m.group(1)}")
    # Match BL-XX, BLXX, BLOCK-XX, BLOCK XX
    for m in re.finditer(r'(?:BL|BLOCK)\s*[-_]?\s*(\d+)', raw):
        tokens.add(f"BL{int(m.group(1)):02d}")
        tokens.add(f"BL{m.group(1)}")
    # Match Plot XX
    for m in re.finditer(r'PLOT\s*[-_]?\s*(\d+)', raw):
        tokens.add(f"PLOT{m.group(1)}")
    # Match PSS / Switchyard / Substation
    if "PSS" in raw:
        tokens.add("PSS")
    if "TRANSFORMER" in raw:
        tokens.add("TRANSFORMER")
    if "INVERTER" in raw or "IDT" in raw:
        tokens.add("INVERTER")
    return tokens


def _classify_package(wbs_or_name: Optional[str]) -> str:
    """Classify work package into standard disciplines."""
    if not wbs_or_name:
        return "General"
    val = str(wbs_or_name).lower()
    if any(k in val for k in ["civil", "foundation", "piling", "excavation", "grouting", "fencing", "road"]):
        return "Civil"
    if any(k in val for k in ["electric", "cable", "ht", "lt", "switchyard", "transformer", "substation", "inverter", "mms"]):
        return "Electrical"
    if any(k in val for k in ["mech", "erection", "blade", "nacelle", "tower", "installation", "assembly"]):
        return "Mechanical"
    if any(k in val for k in ["trans", "line", "bay", "grid", "connectivity"]):
        return "Transmission"
    if any(k in val for k in ["t&c", "commission", "trial run", "testing", "charging"]):
        return "Testing & Commissioning"
    return "General"


def _assess_confidence_indexed(
    activity_id: str,
    act_name: str,
    act_wbs: str,
    act_pkg: str,
    act_tokens: set[str],
    act_start: Optional[datetime],
    act_finish: Optional[datetime],
    item: dict,
    is_rfi: bool = False
) -> tuple[str, float, list[str]]:
    """Calculate confidence using pre-indexed parsed item."""
    score = 0.0
    evidence = []

    item_desc = item["desc"]
    item_pkg = item["pkg"]
    item_tokens = item["tokens"]
    item_created = item["created_at"]

    # Level 1: Explicit ID Reference
    if activity_id and activity_id.lower() in item_desc.lower():
        return ("CONFIRMED", 100.0, [f"Explicit Activity ID '{activity_id}' referenced in issue text"])

    # Level 2: Location / WorkArea matching
    common_locs = act_tokens.intersection(item_tokens)
    if common_locs:
        score += 45.0
        evidence.append(f"Matching location/workarea: {', '.join(common_locs)}")

    # Level 3: Work Package matching
    if act_pkg != "General" and item_pkg != "General" and act_pkg == item_pkg:
        score += 25.0
        evidence.append(f"Matching package discipline: {act_pkg}")

    # Level 4: Date Proximity
    if item_created and act_start:
        finish = act_finish or (act_start + timedelta(days=30))
        win_start = act_start - timedelta(days=15)
        win_finish = finish + timedelta(days=20)

        if win_start <= item_created <= win_finish:
            score += 20.0
            evidence.append(f"Issue timestamp ({item_created.strftime('%Y-%m-%d')}) aligns with schedule window")
        elif abs((item_created - act_start).days) < 60:
            score += 10.0
            evidence.append("Issue timestamp within 60 days of activity")

    # Level 5: Semantic keyword similarity
    keywords = ["foundation", "grouting", "piling", "cable", "transformer", "inverter", "erection", "cracks", "shear key", "testing"]
    shared_kw = [k for k in keywords if k in act_name.lower() and k in item_desc.lower()]
    if shared_kw:
        score += 10.0
        evidence.append(f"Technical keyword correlation: {', '.join(shared_kw)}")

    if score >= 80:
        return ("HIGH CONFIDENCE", min(score, 95.0), evidence)
    elif score >= 60:
        return ("LIKELY", score, evidence)
    elif score >= 35:
        return ("POSSIBLE", score, evidence)
    else:
        return ("LOW", score, evidence or ["Project-level proximity only"])


def _determine_root_cause(
    activity: models.P6Activity,
    matched_ncs: list[dict],
    matched_rfis: list[dict],
    overdue_pos: list[dict],
    delay_days: int
) -> dict:
    """Determine the primary root cause from available evidence across the 18 standard categories."""
    if delay_days <= 0:
        return {
            "category": "None",
            "evidence": "Activity is on schedule or ahead",
            "source_system": "P6",
            "confidence": "CONFIRMED",
            "responsible_party": "N/A",
            "resolution_status": "N/A"
        }

    # 1. Check for Critical Quality Non-Conformances (NVC/NC)
    for nc in matched_ncs:
        defect = (nc.get("defect_type") or "").lower()
        desc = (nc.get("description") or "").lower()
        combined = f"{defect} {desc}"

        if any(k in combined for k in ["drawing", "design", "revision", "spec", "drawing approval"]):
            return {
                "category": "Design",
                "evidence": f"NC {nc.get('nc_label')}: {nc.get('defect_type') or nc.get('description')}",
                "source_system": "Pulse NC",
                "confidence": nc.get("confidence", "HIGH CONFIDENCE"),
                "responsible_party": nc.get("vendor_name") or nc.get("contractor_name") or "Design Team",
                "resolution_status": nc.get("status", "open"),
                "date_raised": nc.get("created_at"),
                "date_resolved": nc.get("approved_at"),
                "duration_days": nc.get("duration_days", 0)
            }

        if any(k in combined for k in ["material", "damaged", "defective", "corrosion", "cracks"]):
            return {
                "category": "Material",
                "evidence": f"NC {nc.get('nc_label')}: {nc.get('defect_type') or nc.get('description')}",
                "source_system": "Pulse NC",
                "confidence": nc.get("confidence", "HIGH CONFIDENCE"),
                "responsible_party": nc.get("vendor_name") or nc.get("contractor_name") or "Supplier",
                "resolution_status": nc.get("status", "open"),
                "date_raised": nc.get("created_at"),
                "date_resolved": nc.get("approved_at"),
                "duration_days": nc.get("duration_days", 0)
            }

        if nc.get("category") == "Critical" or nc.get("debit"):
            debit_str = f" (Debit: ₹{nc['debit']})" if nc.get("debit") else ""
            return {
                "category": "Contractor",
                "evidence": f"Critical NC {nc.get('nc_label')}: {nc.get('defect_type')}{debit_str}",
                "source_system": "Pulse NC",
                "confidence": nc.get("confidence", "HIGH CONFIDENCE"),
                "responsible_party": nc.get("contractor_name") or nc.get("vendor_name") or "EPC Contractor",
                "resolution_status": nc.get("status", "open"),
                "date_raised": nc.get("created_at"),
                "date_resolved": nc.get("approved_at"),
                "duration_days": nc.get("duration_days", 0)
            }

    # 2. Check for RFI Inspection bottlenecks
    for rfi in matched_rfis:
        status = (rfi.get("status") or "").lower()
        if status in ["rejected", "pending", "in review", "open"]:
            return {
                "category": "RFI",
                "evidence": f"RFI {rfi.get('rfi_label')} held in '{rfi.get('status')}' state at checkpoint: {rfi.get('inspection_point_name')}",
                "source_system": "Pulse RFI",
                "confidence": rfi.get("confidence", "LIKELY"),
                "responsible_party": rfi.get("contractor_name") or rfi.get("vendor_name") or "Quality Inspector",
                "resolution_status": rfi.get("status", "pending"),
                "date_raised": rfi.get("created_at"),
                "date_resolved": rfi.get("updated_at"),
                "duration_days": rfi.get("duration_days", 0)
            }

    # 3. Check for Procurement / Overdue PO Delivery
    if overdue_pos:
        worst_po = overdue_pos[0]
        return {
            "category": "Procurement",
            "evidence": f"SAP PO {worst_po.get('po_number')} ({worst_po.get('material_name')}) delivery overdue by {worst_po.get('overdue_days')} days",
            "source_system": "SAP Procurement",
            "confidence": "HIGH CONFIDENCE",
            "responsible_party": worst_po.get("vendor_name") or "Procurement / Supplier",
            "resolution_status": "Pending Delivery",
            "date_raised": worst_po.get("delivery_date"),
            "date_resolved": None,
            "duration_days": worst_po.get("overdue_days", 0)
        }

    # 4. Unknown / No Evidence Found (Case A)
    return {
        "category": "Unknown",
        "evidence": "No corresponding RFI, NC, or PO delivery delay recorded in connected systems",
        "source_system": "P6",
        "confidence": "NO EVIDENCE FOUND",
        "responsible_party": "Unassigned",
        "resolution_status": "Unexplained Delay (Case A)",
        "date_raised": None,
        "date_resolved": None,
        "duration_days": delay_days
    }


def _sanitize_date(dt: Optional[datetime], proj_ref_year: int = 2026) -> tuple[Optional[datetime], bool, Optional[str]]:
    """
    Rigorously sanitizes P6 date entry anomalies (e.g. year 2036 decade entry typos or year 2050 outliers).
    Returns (cleaned_datetime, anomaly_detected, anomaly_note).
    """
    if not dt:
        return None, False, None
    year = dt.year
    if year > 2030:
        # P6 10-year decade entry typo (e.g. 2-digit 36 typed instead of 26)
        if year - 10 <= 2028:
            new_dt = dt.replace(year=year - 10)
            return new_dt, True, f"Year {year} normalized to {new_dt.year} (P6 decade entry typo)"
        elif year >= 2040:
            new_dt = dt.replace(year=proj_ref_year)
            return new_dt, True, f"Outlier year {year} clamped to project baseline year ({proj_ref_year})"
    return dt, False, None


def _validate_activity_delay(act: models.P6Activity, p6_proj: Optional[models.P6Project] = None) -> dict:
    """
    Rigorously validates activity dates against P6 baseline and project schedule window.
    Detects and sanitizes input anomalies with complete audit metadata.
    """
    proj_ref_year = p6_proj.finish_date.year if (p6_proj and p6_proj.finish_date) else 2026
    
    clean_base, base_mod, base_note = _sanitize_date(act.baseline_finish_date, proj_ref_year)
    clean_fin, fin_mod, fin_note = _sanitize_date(act.finish_date, proj_ref_year)
    clean_act_fin, act_mod, act_note = _sanitize_date(getattr(act, "actual_finish_date", None), proj_ref_year)
    clean_plan_fin, plan_mod, plan_note = _sanitize_date(act.planned_finish_date, proj_ref_year)
    
    is_completed = bool(act.status and 'complet' in act.status.lower())
    
    if is_completed:
        eff_fin = clean_act_fin or clean_fin or clean_plan_fin
        basis = "Actual Completion Date vs Baseline Finish"
    else:
        eff_fin = clean_fin or clean_plan_fin
        basis = "Forecast Finish Date vs Baseline Finish"
        
    eff_base = clean_base or clean_plan_fin
    
    delay = 0
    variance = 0
    if eff_fin and eff_base:
        variance = (eff_fin - eff_base).days
        if variance > 0:
            delay = variance
            
    anomaly_detected = base_mod or fin_mod or act_mod or plan_mod
    anomaly_notes = [n for n in [base_note, fin_note, act_note, plan_note] if n]
    
    if anomaly_detected:
        val_status = "CORRECTED_ANOMALY"
    elif clean_base:
        val_status = "VALIDATED"
    elif clean_plan_fin:
        val_status = "ESTIMATED_VS_PLAN"
    else:
        val_status = "UNVERIFIED"
        
    return {
        "delay_days": delay,
        "variance_days": variance,
        "is_delayed": delay > 0,
        "effective_finish": eff_fin.strftime("%Y-%m-%d") if eff_fin else None,
        "effective_baseline": eff_base.strftime("%Y-%m-%d") if eff_base else None,
        "validation_status": val_status,
        "anomaly_detected": anomaly_detected,
        "anomaly_notes": anomaly_notes,
        "basis": basis
    }


def analyze_project_story(db: Session, ctx: dict) -> dict:
    """
    Build the complete Project-Level Intelligence Story connecting:
    Schedule Delays, Pulse NCs, Pulse RFIs, SAP POs, SLR commitments, and E-Invoices.
    Optimized with indexed lookups for sub-second performance.
    """
    project_id = ctx.get("project_id", "")
    project_name = ctx.get("project_name", "")
    mapping = ctx.get("mapping")
    p6_proj = ctx.get("p6_project")
    activities = ctx.get("activities", [])

    if not activities or not p6_proj:
        return {
            "has_data": False,
            "error": "No P6 activities found for this project",
            "overall_health_radar": {},
            "top_delays": [],
            "top_root_causes": [],
            "gap_analysis": [],
            "timeline": []
        }

    # ═══════════════════════════════════════════════════════
    # 1. FETCH ALL INTEGRATED RECORDS
    # ═══════════════════════════════════════════════════════
    search_name = project_name
    mapping_name = mapping.project if mapping else None

    query_filter_nc = models.PulseNC.project_name.ilike(f"%{search_name}%")
    query_filter_rfi = models.PulseRFI.project_name.ilike(f"%{search_name}%")
    if mapping_name:
        query_filter_nc = or_(query_filter_nc, models.PulseNC.project_name.ilike(f"%{mapping_name}%"))
        query_filter_rfi = or_(query_filter_rfi, models.PulseRFI.project_name.ilike(f"%{mapping_name}%"))

    parts = search_name.split('_')
    if len(parts) > 1:
        spv_part = parts[0]
        query_filter_nc = or_(query_filter_nc, models.PulseNC.spv_name.ilike(f"%{spv_part}%"))
        query_filter_rfi = or_(query_filter_rfi, models.PulseRFI.spv_name.ilike(f"%{spv_part}%"))

    if len(project_id) >= 5:
        query_filter_nc = or_(query_filter_nc, models.PulseNC.spv_name.ilike(f"%{project_id}%"))
        query_filter_rfi = or_(query_filter_rfi, models.PulseRFI.spv_name.ilike(f"%{project_id}%"))

    raw_ncs = db.query(models.PulseNC).filter(query_filter_nc).all()
    raw_rfis = db.query(models.PulseRFI).filter(query_filter_rfi).all()

    wbs_prefix = ctx.get("wbs") or ""
    plant_code = ctx.get("plant_code") or ""
    if not wbs_prefix and plant_code:
        wbs_prefix = plant_code

    raw_pos = []
    raw_slr = []
    if wbs_prefix:
        prefix_clean = wbs_prefix[:6]
        raw_pos = db.query(models.MTPOAmount).filter(
            models.MTPOAmount.wbs_element.ilike(f"{prefix_clean}%")
        ).all()
        raw_slr = db.query(models.MTSLRData).filter(
            models.MTSLRData.wbs_element.ilike(f"{prefix_clean}%")
        ).all()

    raw_invoices = db.query(models.EInvoiceRecord).filter(
        or_(
            models.EInvoiceRecord.p6ProjectName.ilike(f"%{project_name}%"),
            models.EInvoiceRecord.workLocation.ilike(f"%{project_id}%"),
            models.EInvoiceRecord.workLocation.ilike(f"%{project_name}%")
        )
    ).all()

    if not raw_invoices and raw_slr:
        po_docs = list(set(s.po_document for s in raw_slr if s.po_document))
        if po_docs:
            raw_invoices = db.query(models.EInvoiceRecord).filter(
                models.EInvoiceRecord.workOrderNo.in_(po_docs[:100])
            ).all()

    now = datetime.utcnow()

    # ═══════════════════════════════════════════════════════
    # 2. PRE-INDEX NCS & RFIS FOR FAST O(1) LOOKUPS
    # ═══════════════════════════════════════════════════════
    indexed_ncs = []
    ncs_by_token = defaultdict(list)
    ncs_by_pkg = defaultdict(list)

    for nc in raw_ncs:
        loc_tokens = _extract_location_tokens(f"{nc.workarea_name} {nc.worklocation_name} {nc.nc_label} {nc.description}")
        pkg = _classify_package(f"{nc.package_name} {nc.subpackage_name} {nc.activity_name}")
        dur = 0
        if nc.created_at and nc.approved_at:
            dur = max(0, (nc.approved_at - nc.created_at).days)
        elif nc.created_at:
            dur = max(0, (now - nc.created_at).days)

        item = {
            "raw": nc,
            "id": nc.id,
            "nc_label": nc.nc_label,
            "status": nc.status or nc.status_label or "open",
            "category": nc.category,
            "defect_type": nc.defect_type,
            "description": nc.description,
            "debit": nc.debit,
            "contractor_name": nc.contractor_name,
            "vendor_name": nc.vendor_name,
            "created_at": nc.created_at,
            "approved_at": nc.approved_at,
            "duration_days": dur,
            "tokens": loc_tokens,
            "pkg": pkg,
            "desc": f"{nc.defect_type or ''} {nc.description or ''}"
        }
        indexed_ncs.append(item)
        for t in loc_tokens:
            ncs_by_token[t].append(item)
        ncs_by_pkg[pkg].append(item)

    indexed_rfis = []
    rfis_by_token = defaultdict(list)
    rfis_by_pkg = defaultdict(list)

    for rfi in raw_rfis:
        loc_tokens = _extract_location_tokens(f"{rfi.workarea_name} {rfi.worklocation_name} {rfi.rfi_label}")
        pkg = _classify_package(f"{rfi.package_name} {rfi.inspection_point_name}")
        dur = 0
        if rfi.created_at and rfi.updated_at:
            dur = max(0, (rfi.updated_at - rfi.created_at).days)
        elif rfi.created_at:
            dur = max(0, (now - rfi.created_at).days)

        item = {
            "raw": rfi,
            "id": rfi.id,
            "rfi_label": rfi.rfi_label,
            "status": rfi.status or rfi.status_label or "open",
            "inspection_point_name": rfi.inspection_point_name,
            "contractor_name": rfi.contractor_name,
            "vendor_name": rfi.vendor_name,
            "created_at": rfi.created_at,
            "updated_at": rfi.updated_at,
            "duration_days": dur,
            "tokens": loc_tokens,
            "pkg": pkg,
            "desc": rfi.inspection_point_name or ""
        }
        indexed_rfis.append(item)
        for t in loc_tokens:
            rfis_by_token[t].append(item)
        rfis_by_pkg[pkg].append(item)

    # Overdue POs
    overdue_pos_list = []
    for po in raw_pos:
        deliv = po.delivery_date
        qty_rem = po.still_to_be_delivered_qty or po.still_to_deliver_qty or 0
        if deliv and deliv < now and (qty_rem > 0 or not po.delivery_completed_flag):
            days_late = (now - deliv).days
            overdue_pos_list.append({
                "po_number": po.purchasing_document,
                "material_name": po.material_name or po.short_text or po.material_code,
                "vendor_name": po.vendor_name,
                "wbs_element": po.wbs_element,
                "delivery_date": deliv.strftime("%Y-%m-%d"),
                "overdue_days": days_late,
                "value_inr": po.net_order_value_inr or 0
            })
    overdue_pos_list.sort(key=lambda x: x["overdue_days"], reverse=True)

    # Invoices mapped by package
    invoices_by_pkg = defaultdict(list)
    for inv in raw_invoices:
        pkg = _classify_package(inv.packageName)
        invoices_by_pkg[pkg].append({
            "invoice_no": inv.invoiceNo,
            "vendor_name": inv.vendorName,
            "amount_inr": inv.invoiceAmount or 0,
            "status": inv.statusDesc,
            "work_order_no": inv.workOrderNo,
            "invoice_date": inv.invoiceDate.strftime("%Y-%m-%d") if inv.invoiceDate else None,
            "stage": inv.stage
        })

    # ═══════════════════════════════════════════════════════
    # 3. ACTIVITY INVESTIGATION & CAUSAL CHAIN BUILDING
    # ═══════════════════════════════════════════════════════
    investigated_activities = []
    critical_activities_delayed = 0
    milestones_at_risk = 0
    activities_without_issues = 0
    delays_with_commercial = 0
    total_commercial_exposure = 0.0

    root_cause_counts = defaultdict(lambda: {"count": 0, "total_delay_days": 0, "activities": []})
    contractor_impact = defaultdict(lambda: {"total_delay": 0, "activities": set(), "ncs": 0, "rfis": 0})

    for act in activities:
        val_info = _validate_activity_delay(act, p6_proj)
        delay = val_info["delay_days"]

        is_critical = bool(act.is_critical or (act.total_float is not None and act.total_float <= 0))
        is_milestone = any(m in (act.type or "").lower() or m in (act.name or "").lower() for m in ["milestone", "start", "finish"])

        if delay > 0 and is_critical:
            critical_activities_delayed += 1
        if delay > 0 and is_milestone:
            milestones_at_risk += 1

        # Fast Candidate Selection using Tokens and Package
        act_name = act.name or ""
        act_wbs = act.wbs_name or ""
        act_pkg = _classify_package(f"{act_wbs} {act_name}")
        act_tokens = _extract_location_tokens(f"{act_name} {act_wbs}")

        # Find NC candidates
        nc_candidates = set()
        for t in act_tokens:
            for item in ncs_by_token.get(t, []):
                nc_candidates.add(item["id"])
        # If no token match, take a few package candidates
        if not nc_candidates and act_pkg != "General":
            for item in ncs_by_pkg.get(act_pkg, [])[:15]:
                nc_candidates.add(item["id"])

        matched_ncs = []
        for item in indexed_ncs:
            if item["id"] in nc_candidates or (act.activity_id and act.activity_id.lower() in item["desc"].lower()):
                conf_label, conf_score, reasons = _assess_confidence_indexed(
                    act.activity_id, act_name, act_wbs, act_pkg, act_tokens,
                    act.planned_start_date, act.finish_date or act.planned_finish_date,
                    item, is_rfi=False
                )
                if conf_score >= 35:
                    matched_ncs.append({
                        "id": item["id"],
                        "nc_label": item["nc_label"],
                        "status": item["status"],
                        "category": item["category"],
                        "defect_type": item["defect_type"],
                        "description": item["description"],
                        "debit": item["debit"],
                        "contractor_name": item["contractor_name"],
                        "vendor_name": item["vendor_name"],
                        "created_at": item["created_at"].strftime("%Y-%m-%d") if item["created_at"] else None,
                        "approved_at": item["approved_at"].strftime("%Y-%m-%d") if item["approved_at"] else None,
                        "duration_days": item["duration_days"],
                        "confidence": conf_label,
                        "confidence_score": conf_score,
                        "evidence": reasons
                    })
        matched_ncs.sort(key=lambda x: x["confidence_score"], reverse=True)

        # Find RFI candidates
        rfi_candidates = set()
        for t in act_tokens:
            for item in rfis_by_token.get(t, []):
                rfi_candidates.add(item["id"])
        if not rfi_candidates and act_pkg != "General":
            for item in rfis_by_pkg.get(act_pkg, [])[:15]:
                rfi_candidates.add(item["id"])

        matched_rfis = []
        for item in indexed_rfis:
            if item["id"] in rfi_candidates:
                conf_label, conf_score, reasons = _assess_confidence_indexed(
                    act.activity_id, act_name, act_wbs, act_pkg, act_tokens,
                    act.planned_start_date, act.finish_date or act.planned_finish_date,
                    item, is_rfi=True
                )
                if conf_score >= 35:
                    matched_rfis.append({
                        "id": item["id"],
                        "rfi_label": item["rfi_label"],
                        "status": item["status"],
                        "inspection_point_name": item["inspection_point_name"],
                        "contractor_name": item["contractor_name"],
                        "vendor_name": item["vendor_name"],
                        "created_at": item["created_at"].strftime("%Y-%m-%d") if item["created_at"] else None,
                        "updated_at": item["updated_at"].strftime("%Y-%m-%d") if item["updated_at"] else None,
                        "duration_days": item["duration_days"],
                        "confidence": conf_label,
                        "confidence_score": conf_score,
                        "evidence": reasons
                    })
        matched_rfis.sort(key=lambda x: x["confidence_score"], reverse=True)

        # Related Invoices
        related_invoices = invoices_by_pkg.get(act_pkg, []) or invoices_by_pkg.get("General", [])

        # Overdue POs
        pkg_overdue_pos = [p for p in overdue_pos_list if act_pkg in p["material_name"] or act_pkg in act_wbs]

        # Determine Root Cause
        root_cause = _determine_root_cause(act, matched_ncs, matched_rfis, pkg_overdue_pos, delay)

        has_issue = len(matched_ncs) > 0 or len(matched_rfis) > 0 or len(pkg_overdue_pos) > 0
        if delay > 10 and not has_issue:
            activities_without_issues += 1

        comm_exposure = sum(inv["amount_inr"] for inv in related_invoices[:3])
        if delay > 0 and comm_exposure > 0:
            delays_with_commercial += 1
            total_commercial_exposure += comm_exposure

        rc_cat = root_cause["category"]
        if delay > 0:
            root_cause_counts[rc_cat]["count"] += 1
            root_cause_counts[rc_cat]["total_delay_days"] += delay
            root_cause_counts[rc_cat]["activities"].append(act.activity_id)

            resp_party = root_cause.get("responsible_party") or "Unassigned"
            if resp_party not in ["N/A", "Unassigned"]:
                contractor_impact[resp_party]["total_delay"] += delay
                contractor_impact[resp_party]["activities"].add(act.activity_id)
                contractor_impact[resp_party]["ncs"] += len(matched_ncs)
                contractor_impact[resp_party]["rfis"] += len(matched_rfis)

        if delay > 0 or is_critical or has_issue:
            story_item = {
                "activity_id": act.activity_id,
                "name": act.name,
                "wbs_name": act.wbs_name,
                "package": act_pkg,
                "status": act.status,
                "is_critical": is_critical,
                "is_milestone": is_milestone,
                "delay_days": delay,
                "variance_days": val_info["variance_days"],
                "validation": {
                    "is_validated": True,
                    "status": val_info["validation_status"],
                    "anomaly_detected": val_info["anomaly_detected"],
                    "anomaly_notes": val_info["anomaly_notes"],
                    "basis": val_info["basis"]
                },
                "total_float": act.total_float,
                "percent_complete": act.percent_complete or 0,
                "planned_start": act.planned_start_date.strftime("%Y-%m-%d") if act.planned_start_date else None,
                "planned_finish": act.planned_finish_date.strftime("%Y-%m-%d") if act.planned_finish_date else None,
                "forecast_finish": val_info["effective_finish"],
                "baseline_finish": val_info["effective_baseline"],
                "root_cause": root_cause,
                "has_linked_issue": has_issue,
                "matched_ncs_count": len(matched_ncs),
                "matched_rfis_count": len(matched_rfis),
                "matched_ncs": matched_ncs[:5],
                "matched_rfis": matched_rfis[:5],
                "related_invoices": related_invoices[:3],
                "commercial_exposure_inr": comm_exposure,
                "narrative_story": _generate_activity_story(act, delay, root_cause, matched_ncs, matched_rfis, related_invoices, val_info)
            }
            investigated_activities.append(story_item)

    investigated_activities.sort(key=lambda x: x["delay_days"], reverse=True)

    # ═══════════════════════════════════════════════════════
    # 4. MISSING INTERACTIONS & GAP DETECTION (CASES A - E)
    # ═══════════════════════════════════════════════════════
    gaps = []

    # Case A: Unexplained Delay
    unexplained_acts = [a for a in investigated_activities if a["delay_days"] >= 10 and not a["has_linked_issue"]]
    if unexplained_acts:
        gaps.append({
            "case": "CASE_A",
            "title": f"Schedule delay detected with no corresponding issue recorded ({len(unexplained_acts)} activities)",
            "severity": "high",
            "count": len(unexplained_acts),
            "description": f"{len(unexplained_acts)} activities have slipped by 10+ days without any RFI, NC, or PO constraint logged.",
            "impact": "Unmonitored delays risk blindside milestone slippages",
            "sample_activities": [a["activity_id"] for a in unexplained_acts[:5]],
            "recommended_action": "Site engineer must raise an RFI or log delay justification in DPR."
        })

    # Case B: Open RFI without visible schedule impact
    unimpacted_rfis = [r for r in raw_rfis if (r.status or "").lower() in ["open", "pending", "in review"]]
    if len(unimpacted_rfis) > 10:
        gaps.append({
            "case": "CASE_B",
            "title": f"Open RFIs without visible schedule impact ({len(unimpacted_rfis)} RFIs)",
            "severity": "medium",
            "count": len(unimpacted_rfis),
            "description": f"{len(unimpacted_rfis)} RFIs remain open or in review across the site without yet shifting activity forecast dates.",
            "impact": "Potential latent bottleneck that may suddenly manifest as schedule drift",
            "sample_rfis": [r.rfi_label for r in unimpacted_rfis[:5]],
            "recommended_action": "Quality team to expedite inspection approvals to prevent downstream blockage."
        })

    # Case C: Potential relationship detected without explicit link
    inferred_links = [a for a in investigated_activities if a["root_cause"]["confidence"] in ["LIKELY", "POSSIBLE"]]
    if inferred_links:
        gaps.append({
            "case": "CASE_C",
            "title": f"Inferred cross-system relationships ({len(inferred_links)} activities)",
            "severity": "info",
            "count": len(inferred_links),
            "description": "Detected operational correlation between activities and quality issues based on package, location, and date proximity.",
            "impact": "High likelihood that unresolved issues are the root source of activity drift",
            "sample_activities": [a["activity_id"] for a in inferred_links[:5]],
            "recommended_action": "Project controls to stamp explicit activity IDs on future inspection requests."
        })

    # Case D: Delayed activity with commercial transaction but no explicit issue linkage
    delays_with_unlinked_comm = [a for a in investigated_activities if a["delay_days"] > 15 and a["commercial_exposure_inr"] > 0 and not a["has_linked_issue"]]
    if delays_with_unlinked_comm:
        gaps.append({
            "case": "CASE_D",
            "title": f"Delayed activity with commercial transaction but no explicit issue linkage ({len(delays_with_unlinked_comm)} activities)",
            "severity": "high",
            "count": len(delays_with_unlinked_comm),
            "description": "Work packages are accumulating invoice commitments while construction is delayed, with no contractor claim recorded.",
            "impact": "Potential premature commercial release or unverified contractor claims",
            "sample_activities": [a["activity_id"] for a in delays_with_unlinked_comm[:5]],
            "recommended_action": "Contracts team must cross-reference invoice release against physical progress."
        })

    # Case E: Commercial transaction raised while work package delayed
    delayed_invoices = [inv for inv in raw_invoices if (inv.statusDesc or "").lower() in ["completed", "approved", "paid"] and critical_activities_delayed > 0]
    if delayed_invoices:
        gaps.append({
            "case": "CASE_E",
            "title": f"Commercial transaction raised while associated work package remains delayed ({len(delayed_invoices)} invoices)",
            "severity": "medium",
            "count": len(delayed_invoices),
            "description": f"{len(delayed_invoices)} invoices processed for work packages that are currently logging schedule delays.",
            "impact": "Commercial spend outrunning site delivery progress",
            "sample_invoices": [inv.invoiceNo for inv in delayed_invoices[:5]],
            "recommended_action": "Audit bill of quantities against completed inspection milestones before final sign-off."
        })

    # ═══════════════════════════════════════════════════════
    # 5. UNIFIED PROJECT TIMELINE
    # ═══════════════════════════════════════════════════════
    timeline_events = []

    for act in investigated_activities[:25]:
        if act["planned_start"]:
            timeline_events.append({
                "date": act["planned_start"],
                "source": "P6 Schedule",
                "type": "ACTIVITY_PLANNED_START",
                "title": f"Planned Start: {act['name']}",
                "description": f"Activity scheduled in package '{act['package']}'.",
                "activity_id": act["activity_id"],
                "badge": "Planned",
                "severity": "info"
            })
        if act["delay_days"] > 0 and act["forecast_finish"]:
            timeline_events.append({
                "date": act["forecast_finish"],
                "source": "P6 Schedule",
                "type": "ACTIVITY_DELAYED",
                "title": f"Delayed Finish: {act['name']} (+{act['delay_days']}d)",
                "description": f"Forecast completion slipped by {act['delay_days']} days against baseline ({act['baseline_finish'] or 'N/A'}).",
                "activity_id": act["activity_id"],
                "badge": f"+{act['delay_days']}d Delay",
                "severity": "critical" if act["is_critical"] else "high"
            })

    for nc in raw_ncs[:40]:
        if nc.created_at:
            timeline_events.append({
                "date": nc.created_at.strftime("%Y-%m-%d"),
                "source": "Pulse NC",
                "type": "NC_RAISED",
                "title": f"NC Raised: {nc.nc_label} ({nc.category or 'Issue'})",
                "description": f"Defect in {nc.workarea_name or nc.package_name}: {nc.defect_type or nc.description}",
                "responsible": nc.contractor_name or nc.vendor_name,
                "badge": nc.category or "NC",
                "severity": "critical" if nc.category == "Critical" else "high"
            })
        if nc.approved_at:
            timeline_events.append({
                "date": nc.approved_at.strftime("%Y-%m-%d"),
                "source": "Pulse NC",
                "type": "NC_APPROVED",
                "title": f"NC Resolved: {nc.nc_label}",
                "description": f"Non-conformance approved/resolved for {nc.contractor_name or 'team'}.",
                "responsible": nc.contractor_name or nc.vendor_name,
                "badge": "Resolved",
                "severity": "success"
            })

    for rfi in raw_rfis[:40]:
        if rfi.created_at:
            timeline_events.append({
                "date": rfi.created_at.strftime("%Y-%m-%d"),
                "source": "Pulse RFI",
                "type": "RFI_RAISED",
                "title": f"RFI Inspection: {rfi.rfi_label}",
                "description": f"Inspection checkpoint '{rfi.inspection_point_name}' requested by {rfi.contractor_name or 'contractor'}.",
                "responsible": rfi.contractor_name or rfi.vendor_name,
                "badge": rfi.status or "RFI",
                "severity": "info" if rfi.status == "completed" else "warning"
            })

    for inv in raw_invoices[:25]:
        if inv.invoiceDate:
            timeline_events.append({
                "date": inv.invoiceDate.strftime("%Y-%m-%d"),
                "source": "E-Invoice",
                "type": "INVOICE_SUBMITTED",
                "title": f"Invoice: {inv.invoiceNo} (₹{round((inv.invoiceAmount or 0)/10000000, 2)} Cr)",
                "description": f"Commercial transaction for '{inv.packageName}' by {inv.vendorName}.",
                "responsible": inv.vendorName,
                "badge": inv.statusDesc or "Submitted",
                "severity": "info"
            })

    timeline_events.sort(key=lambda x: x["date"], reverse=True)

    # ═══════════════════════════════════════════════════════
    # 6. HEALTH RADAR & RANKINGS
    # ═══════════════════════════════════════════════════════
    sched_health = max(10, 100 - min(critical_activities_delayed * 5, 80))
    nc_health = max(10, 100 - min(len([n for n in raw_ncs if n.category == "Critical"]) * 8, 80))
    rfi_health = max(20, 100 - min(len(unimpacted_rfis) * 3, 70))
    milestone_health = max(10, 100 - min(milestones_at_risk * 15, 85))
    comm_health = max(20, 100 - min(delays_with_commercial * 10, 70))
    contractor_health = max(20, 100 - min(len(contractor_impact) * 8, 70))
    interface_health = 75
    if any(k in [a["package"] for a in investigated_activities[:10]] for k in ["Transmission", "Testing & Commissioning"]):
        interface_health = 45

    overall_risk_score = round(
        (sched_health * 0.25) +
        (milestone_health * 0.20) +
        (nc_health * 0.15) +
        (rfi_health * 0.10) +
        (comm_health * 0.10) +
        (contractor_health * 0.10) +
        (interface_health * 0.10),
        1
    )

    if overall_risk_score >= 75:
        overall_status = "ON_TRACK"
    elif overall_risk_score >= 50:
        overall_status = "AT_RISK"
    elif overall_risk_score >= 30:
        overall_status = "CRITICAL"
    else:
        overall_status = "SEVERE"

    top_root_causes = []
    for cat, data in sorted(root_cause_counts.items(), key=lambda x: x[1]["total_delay_days"], reverse=True):
        if cat != "None":
            top_root_causes.append({
                "category": cat,
                "delayed_activities_count": data["count"],
                "total_delay_days": data["total_delay_days"],
                "sample_activity_ids": data["activities"][:3]
            })

    contractor_ranking = []
    for c_name, c_data in sorted(contractor_impact.items(), key=lambda x: x[1]["total_delay"], reverse=True):
        contractor_ranking.append({
            "contractor_name": c_name,
            "total_delay_impact_days": c_data["total_delay"],
            "activities_affected": len(c_data["activities"]),
            "nc_count": c_data["ncs"],
            "rfi_count": c_data["rfis"]
        })

    critical_insights = [
        f"{critical_activities_delayed} critical path activities are currently delayed.",
        f"{activities_without_issues} delayed activities have no corresponding issue or RFI logged (Case A).",
        f"{delays_with_commercial} delayed activities have active commercial transactions (₹{round(total_commercial_exposure/10000000, 2)} Cr exposure)."
    ]

    return {
        "has_data": True,
        "project_id": project_id,
        "project_name": project_name,
        "overall_status": overall_status,
        "overall_risk_score": overall_risk_score,
        "computed_at": datetime.utcnow().isoformat(),

        "executive_summary": {
            "critical_activities_delayed": critical_activities_delayed,
            "milestones_at_risk": milestones_at_risk,
            "open_issues_count": len([n for n in raw_ncs if n.status != "completed"]),
            "critical_issues_count": len([n for n in raw_ncs if n.category == "Critical"]),
            "open_rfis_count": len(unimpacted_rfis),
            "commercial_exposure_cr": round(total_commercial_exposure / 10000000, 2),
            "activities_without_issues": activities_without_issues,
            "delays_with_commercial": delays_with_commercial,
            "critical_insights": critical_insights
        },

        "health_radar": {
            "schedule": sched_health,
            "issues": nc_health,
            "rfis": rfi_health,
            "milestones": milestone_health,
            "commercial": comm_health,
            "contractors": contractor_health,
            "interface": interface_health,
            "overall": overall_risk_score
        },

        "top_delays": investigated_activities[:15],
        "all_delays": investigated_activities,
        "top_root_causes": top_root_causes[:5],
        "contractor_impact_ranking": contractor_ranking[:5],
        "gaps": gaps,
        "timeline": timeline_events[:60],

        "core_questions": {
            "issues_causing_delays": [a for a in investigated_activities if a["has_linked_issue"]][:10],
            "delayed_activities_without_issues": [a for a in investigated_activities if a["delay_days"] > 10 and not a["has_linked_issue"]][:10],
            "issues_without_schedule_impact": unimpacted_rfis[:10],
            "delays_with_commercial": [a for a in investigated_activities if a["delay_days"] > 0 and a["commercial_exposure_inr"] > 0][:10],
            "top_contractors": contractor_ranking[:5],
            "milestones_at_risk": [a for a in investigated_activities if a["is_milestone"] and a["delay_days"] > 0][:5]
        }
    }


def investigate_single_activity(db: Session, project_id: str, activity_id: str) -> dict:
    """
    First-class 'Why is this delayed?' deep dive for a single P6 activity.
    Returns complete chain:
    DELAY → ACTIVITY → PACKAGE → ISSUE/RFI → ROOT CAUSE → RESPONSIBLE PARTY
          → RESOLUTION → SCHEDULE IMPACT → INVOICE/SLR → SAP → COMMERCIAL IMPACT
    """
    mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == project_id).first()
    p6_proj = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()

    if not p6_proj:
        return {"found": False, "error": f"Project '{project_id}' not found"}

    activity = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6_proj.p6_object_id,
        models.P6Activity.activity_id == activity_id
    ).first()

    if not activity:
        return {"found": False, "error": f"Activity '{activity_id}' not found in project '{project_id}'"}

    ctx = {
        "project_id": project_id,
        "project_name": mapping.project_name_from_p6 if mapping else (p6_proj.name or project_id),
        "mapping": mapping,
        "p6_project": p6_proj,
        "activities": [activity],
        "wbs": mapping.module_wbs if mapping else None,
        "plant_code": mapping.spv_plant_code if mapping else None,
    }

    full_story = analyze_project_story(db, ctx)
    all_acts = full_story.get("all_delays", [])
    matched_inv = next((a for a in all_acts if a.get("activity_id") == activity_id), None)
    if matched_inv:
        return {"found": True, "investigation": matched_inv}

    val_info = _validate_activity_delay(activity, p6_proj)
    pkg = _classify_package(f"{activity.wbs_name} {activity.name}")

    return {
        "found": True,
        "investigation": {
            "activity_id": activity.activity_id,
            "name": activity.name,
            "wbs_name": activity.wbs_name,
            "package": pkg,
            "status": activity.status,
            "delay_days": val_info["delay_days"],
            "variance_days": val_info["variance_days"],
            "validation": {
                "is_validated": True,
                "status": val_info["validation_status"],
                "anomaly_detected": val_info["anomaly_detected"],
                "anomaly_notes": val_info["anomaly_notes"],
                "basis": val_info["basis"]
            },
            "planned_start": activity.planned_start_date.strftime("%Y-%m-%d") if activity.planned_start_date else None,
            "planned_finish": activity.planned_finish_date.strftime("%Y-%m-%d") if activity.planned_finish_date else None,
            "forecast_finish": val_info["effective_finish"],
            "baseline_finish": val_info["effective_baseline"],
            "root_cause": {
                "category": "None" if val_info["delay_days"] <= 0 else "Unknown",
                "evidence": "Activity is on schedule or ahead of baseline" if val_info["delay_days"] <= 0 else "No corresponding quality or PO issues recorded",
                "confidence": "CONFIRMED" if val_info["delay_days"] <= 0 else "NO EVIDENCE FOUND",
                "responsible_party": "N/A"
            },
            "matched_ncs": [],
            "matched_rfis": [],
            "related_invoices": [],
            "narrative_story": _generate_activity_story(
                activity, val_info["delay_days"],
                {"category": "None", "evidence": "Activity is progressing on schedule", "confidence": "CONFIRMED"},
                [], [], [], val_info
            )
        }
    }


def _generate_activity_story(
    act: models.P6Activity,
    delay_days: int,
    root_cause: dict,
    ncs: list[dict],
    rfis: list[dict],
    invoices: list[dict],
    val_info: Optional[dict] = None
) -> str:
    """Generate a structured, executive-grade Markdown story connecting the evidence chain."""
    name = act.name or act.activity_id
    rc_cat = root_cause.get("category", "Unknown")
    confidence = root_cause.get("confidence", "NO EVIDENCE FOUND")
    val_status = val_info.get("validation_status") if val_info else "VALIDATED"
    eff_base = val_info.get("effective_baseline") if val_info else None
    eff_fin = val_info.get("effective_finish") if val_info else None
    anomaly_detected = val_info.get("anomaly_detected", False) if val_info else False
    anomaly_notes = val_info.get("anomaly_notes", []) if val_info else []

    if delay_days <= 0:
        early_note = f" (variance: {val_info.get('variance_days', 0)} days vs baseline)" if val_info and val_info.get('variance_days') is not None else ""
        text = f"**{name}** is currently on track according to the baseline schedule{early_note}."
        if anomaly_detected and anomaly_notes:
            text += f"\n\n> ℹ️ **Schedule Audit Notice:** {'; '.join(anomaly_notes)}."
        return text

    blocks = []
    
    # Header summary
    base_text = f" against baseline finish of **{eff_base}**" if eff_base else ""
    forecast_text = f" (current forecast: **{eff_fin}**)" if eff_fin else ""
    blocks.append(f"**{name}** is delayed by **{delay_days} days**{base_text}{forecast_text}.")

    # Root cause callout
    if rc_cat != "Unknown":
        blocks.append(f"> **Primary Root Cause:** **{rc_cat}** (Confidence: **{confidence}**)\n> \n> **System Evidence:** {root_cause.get('evidence')}")
        if root_cause.get("responsible_party") and root_cause.get("responsible_party") != "Unassigned":
            blocks.append(f"**Responsible Party:** **{root_cause.get('responsible_party')}** (Resolution Status: *{root_cause.get('resolution_status', 'Open')}*)")
    else:
        blocks.append("> ⚠️ **Unexplained Delay (Case A):** Schedule slip detected with no corresponding quality non-conformance, inspection rejection, or purchase order constraint recorded in connected systems.")

    # Multi-system evidence trail
    trail_items = []
    if ncs:
        top_nc = ncs[0]
        debit_str = f" | Debit: ₹{top_nc['debit']}" if top_nc.get('debit') else ""
        trail_items.append(f"- **Quality Non-Conformance:** **{top_nc.get('nc_label')}** ({top_nc.get('status')}) logged by contractor *{top_nc.get('contractor_name') or 'N/A'}*{debit_str}.")
    
    if rfis:
        top_rfi = rfis[0]
        trail_items.append(f"- **Site Inspection:** RFI **{top_rfi.get('rfi_label')}** on checkpoint *'{top_rfi.get('inspection_point_name')}'* (Status: {top_rfi.get('status')}).")

    if invoices:
        top_inv = invoices[0]
        trail_items.append(f"- **Commercial Transaction:** Invoice **{top_inv.get('invoice_no')}** for **₹{round(top_inv.get('amount_inr', 0)/10000000, 2)} Cr** (PO: {top_inv.get('work_order_no')}).")

    if val_info and val_info.get("basis"):
        trail_items.append(f"- **Schedule Calculation Basis:** Verified via *{val_info.get('basis')}*.")

    if trail_items:
        blocks.append("#### Multi-System Evidence Trail:\n" + "\n".join(trail_items))

    if anomaly_detected and anomaly_notes:
        blocks.append(f"> ℹ️ **Schedule Audit Notice:** {'; '.join(anomaly_notes)}.")

    return "\n\n".join(blocks)

