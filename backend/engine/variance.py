"""
Akasha Deterministic Variance Calculation Engine — Phase 1

Every numeric field produced by this module is traceable to either:
  (a) a direct database query, or
  (b) a deterministic Python calculation.

No LLM calls. No guessing. No hallucination.
"""

import logging
import json
from datetime import datetime, date
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# PHASE KEYWORD MAP
# Maps activity names to construction phases via keyword matching.
# Source: audit of 95K mapped activities across 59 projects.
# ═══════════════════════════════════════════════════════════
PHASE_KEYWORDS = {
    "Foundation": ["foundation", "piling", "pile", "augur", "concret", "footing"],
    "Erection/Structure": ["erection", "structure", "tracker", "mms", "purlin", "rafter"],
    "Module Installation": ["module", "inverter", "panel mount", "pv install"],
    "Cabling": ["cable", "stringing", "fiber", "earthing", "conduit", "wiring"],
    "Commissioning": ["commission", "grid", "switchyard", "energi", "charging", "synchron"],
    "WTG": ["wtg"],
    "Transformer": ["transformer"],
    "Manufacturing": ["manufactur", "dispatch", "receipt", "delivery"],
}


def _classify_phase(activity_name: str) -> str:
    """Classify an activity into a construction phase by keyword matching."""
    name_lower = (activity_name or "").lower()
    for phase, keywords in PHASE_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return phase
    return "Other"


def _safe_drift_days(finish_date, baseline_finish_date) -> int | None:
    """Compute drift in days between forecast finish and baseline finish.
    Returns None if either date is missing.
    Positive = behind schedule, Negative = ahead of schedule.
    """
    if not finish_date or not baseline_finish_date:
        return None
    delta = finish_date - baseline_finish_date
    return delta.days


def _safe_date_str(dt) -> str | None:
    """Convert a datetime to ISO date string, or None."""
    if dt is None:
        return None
    if isinstance(dt, (datetime, date)):
        return dt.strftime("%Y-%m-%d")
    return str(dt)


# ═══════════════════════════════════════════════════════════
# 1. P6 SCHEDULE VARIANCE
# ═══════════════════════════════════════════════════════════

def compute_p6_variance(db: Session, project_id: str) -> dict:
    """
    Compute deterministic schedule variance from P6 activity data.

    Data path: project_mapping.project_id → p6_project → p6_activity
    
    For each activity with baseline dates:
    - drift_days = (forecast_finish - baseline_finish).days
    - is_critical = total_float <= 0
    
    Returns structured variance data grouped by construction phase.
    """
    # Resolve the P6 project
    p6_proj = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()

    if not p6_proj:
        return {
            "project_id": project_id,
            "project_name": None,
            "data_date": None,
            "summary": {
                "total_activities": 0,
                "baselined_activities": 0,
                "drifted_activities": 0,
                "critical_activities": 0,
                "avg_finish_drift_days": 0,
                "max_finish_drift_days": 0,
            },
            "phase_variance": [],
            "schedule_impact": [0, 0, 0],
            "top_drifters": [],
        }

    # Query all activities for this project
    activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6_proj.p6_object_id
    ).all()

    # ── Per-activity variance calculation ──
    all_drifts = []
    phase_buckets = defaultdict(list)

    for act in activities:
        # Only compute drift for activities that have baselines
        drift = _safe_drift_days(act.finish_date, act.baseline_finish_date)
        phase = _classify_phase(act.name)

        is_critical = (
            act.total_float is not None and act.total_float <= 0
        )

        entry = {
            "activity_id": act.activity_id,
            "name": act.name,
            "status": act.status,
            "phase": phase,
            "drift_days": drift,
            "float_hours": act.total_float,
            "is_critical": is_critical,
            "planned_duration": act.planned_duration,
            "actual_duration": act.actual_duration,
            "remaining_duration": act.remaining_duration,
            "percent_complete": act.percent_complete,
            "baseline_start": _safe_date_str(act.baseline_start_date),
            "baseline_finish": _safe_date_str(act.baseline_finish_date),
            "forecast_start": _safe_date_str(act.start_date),
            "forecast_finish": _safe_date_str(act.finish_date),
        }

        if drift is not None:
            all_drifts.append(entry)
        phase_buckets[phase].append(entry)

    # ── Phase-level aggregation ──
    phase_variance = []
    for phase_name, entries in sorted(phase_buckets.items()):
        drifted = [e for e in entries if e["drift_days"] is not None and e["drift_days"] > 0]
        critical = [e for e in entries if e["is_critical"]]
        drift_values = [e["drift_days"] for e in entries if e["drift_days"] is not None]

        avg_drift = round(sum(drift_values) / len(drift_values), 1) if drift_values else 0
        max_drift = max(drift_values) if drift_values else 0

        # Top 3 worst drifters in this phase
        worst = sorted(
            [e for e in entries if e["drift_days"] is not None],
            key=lambda x: x["drift_days"],
            reverse=True
        )[:3]

        sample_activities = [
            {
                "activity_id": w["activity_id"],
                "name": w["name"],
                "drift_days": w["drift_days"],
                "float_hours": w["float_hours"],
                "status": w["status"],
            }
            for w in worst
        ]

        phase_variance.append({
            "phase": phase_name,
            "total": len(entries),
            "drifted": len(drifted),
            "critical_count": len(critical),
            "avg_drift_days": avg_drift,
            "max_drift_days": max_drift,
            "sample_activities": sample_activities,
        })

    # Sort phases: most drifted first
    phase_variance.sort(key=lambda x: x["avg_drift_days"], reverse=True)

    # ── Project-level schedule_impact array ──
    # [Foundation avg drift, Module Installation avg drift, Commissioning avg drift]
    phase_drift_map = {pv["phase"]: pv["avg_drift_days"] for pv in phase_variance}
    schedule_impact = [
        round(phase_drift_map.get("Foundation", 0)),
        round(phase_drift_map.get("Module Installation", 0)),
        round(phase_drift_map.get("Commissioning", 0)),
    ]

    # ── Summary ──
    baselined = [e for e in all_drifts]
    drifted_all = [e for e in all_drifts if e["drift_days"] > 0]
    critical_all = [e for e in all_drifts if e["is_critical"]]
    drift_vals = [e["drift_days"] for e in all_drifts]

    summary = {
        "total_activities": len(activities),
        "baselined_activities": len(baselined),
        "drifted_activities": len(drifted_all),
        "critical_activities": len(critical_all),
        "avg_finish_drift_days": round(sum(drift_vals) / len(drift_vals), 1) if drift_vals else 0,
        "max_finish_drift_days": max(drift_vals) if drift_vals else 0,
    }

    # ── Top 10 worst drifters across all phases ──
    top_drifters = sorted(
        all_drifts,
        key=lambda x: x["drift_days"],
        reverse=True
    )[:10]

    top_drifter_output = [
        {
            "activity_id": d["activity_id"],
            "name": d["name"],
            "phase": d["phase"],
            "drift_days": d["drift_days"],
            "float_hours": d["float_hours"],
            "status": d["status"],
            "baseline_finish": d["baseline_finish"],
            "forecast_finish": d["forecast_finish"],
        }
        for d in top_drifters
    ]

    return {
        "project_id": project_id,
        "project_name": p6_proj.name,
        "data_date": _safe_date_str(p6_proj.data_date),
        "summary": summary,
        "phase_variance": phase_variance,
        "schedule_impact": schedule_impact,
        "top_drifters": top_drifter_output,
    }


# ═══════════════════════════════════════════════════════════
# 2. SAP SUPPLY CHAIN VARIANCE
# ═══════════════════════════════════════════════════════════

def compute_sap_variance(db: Session, project_id: str) -> dict:
    """
    Compute deterministic supply chain variance from SAP data.

    Data path: project_mapping.module_wbs → mt_poamount, mt_materialdocument, mt_inventory
    
    Three SAP tables:
    - ZSPS (mt_poamount): Purchase orders — ordered vs delivered vs pending
    - MB51 (mt_materialdocument): Material consumption movements (221=issue, 222=return)
    - MB52 (mt_inventory): Current stock on hand
    
    Supply gap = ordered - consumed - inventory (deterministic formula)
    """
    # Resolve project mapping to get WBS element
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()

    empty_result = {
        "summary": {
            "total_po_count": 0,
            "total_ordered_qty": 0,
            "total_delivered_qty": 0,
            "fulfillment_pct": 0,
            "total_pending_qty": 0,
            "consumed_qty": 0,
            "consumed_value_inr": 0,
            "inventory_qty": 0,
            "inventory_value_inr": 0,
            "supply_gap_qty": 0,
        },
        "material_gaps": [],
        "vendor_risk": [],
    }

    if not mapping:
        return empty_result

    wbs_exact = None
    if mapping.module_wbs and str(mapping.module_wbs).strip().lower() not in ('nan', 'none', 'null', ''):
        wbs_exact = str(mapping.module_wbs).strip()

    if not wbs_exact:
        return empty_result

    # ── ZSPS: Purchase Orders ──
    po_records = db.query(models.MTPOAmount).filter(
        models.MTPOAmount.wbs_element == wbs_exact
    ).all()

    po_materials = set()
    for po in po_records:
        if po.material_code:
            mat_str = str(po.material_code).strip().lstrip('0')
            if mat_str:
                po_materials.add(mat_str)

    total_ordered = 0.0
    total_delivered = 0.0
    total_pending = 0.0
    total_po_value = 0.0

    # Material-level aggregation
    material_agg = defaultdict(lambda: {
        "ordered": 0, "delivered": 0, "pending": 0, "material_name": ""
    })
    # Vendor-level aggregation
    vendor_agg = defaultdict(lambda: {
        "total_ordered": 0, "total_pending": 0, "po_count": 0
    })

    for po in po_records:
        ordered = po.order_quantity or 0
        delivered = po.delivered_qty or 0
        pending = po.still_to_deliver_qty or 0
        # If still_to_deliver is 0 but ordered > delivered, compute it
        if pending == 0 and ordered > delivered:
            pending = ordered - delivered

        total_ordered += ordered
        total_delivered += delivered
        total_pending += pending
        total_po_value += (po.net_order_value_inr or 0)

        mat_key = po.material_name or po.material_code or "Unknown"
        material_agg[mat_key]["ordered"] += ordered
        material_agg[mat_key]["delivered"] += delivered
        material_agg[mat_key]["pending"] += pending
        material_agg[mat_key]["material_name"] = mat_key

        vendor_key = po.vendor_name or "Unknown"
        vendor_agg[vendor_key]["total_ordered"] += ordered
        vendor_agg[vendor_key]["total_pending"] += pending
        vendor_agg[vendor_key]["po_count"] += 1

    # ── MB51: Material Consumption ──
    mb51_records = db.query(models.MTMaterialDocument).filter(
        models.MTMaterialDocument.wbs_element == wbs_exact
    ).all()

    consumed_qty = 0.0
    consumed_value_inr = 0.0
    for rec in mb51_records:
        mat_str = str(rec.material_code).strip().lstrip('0') if rec.material_code else ''
        # Only count consumption for materials that have POs
        if mat_str not in po_materials and po_materials:
            continue
        qty = abs(rec.quantity or 0)
        val = abs(rec.amount_in_lc or 0)
        mvt = str(rec.movement_type).strip()
        if mvt == "222":
            # Return movement — subtract from consumption
            consumed_qty -= qty
            consumed_value_inr -= val
        else:
            # Issue movement (221 and others) — add to consumption
            consumed_qty += qty
            consumed_value_inr += val

    # ── MB52: Inventory ──
    mb52_records = db.query(models.MTInventory).filter(
        models.MTInventory.wbs_element == wbs_exact,
        models.MTInventory.quantity_inv > 0
    ).all()

    inventory_qty = 0.0
    inventory_value_inr = 0.0
    for inv in mb52_records:
        mat_str = str(inv.material_code).strip().lstrip('0') if inv.material_code else ''
        if mat_str in po_materials or not po_materials:
            inventory_qty += (inv.quantity_inv or 0)
            inventory_value_inr += (inv.value_unrestricted or 0)

    # ── Supply Gap (deterministic formula) ──
    supply_gap = max(0, total_ordered - consumed_qty - inventory_qty)

    fulfillment_pct = round(
        (total_delivered / total_ordered * 100) if total_ordered > 0 else 0, 1
    )

    # ── Material Gaps (sorted by gap severity) ──
    material_gaps = []
    for mat_key, agg in material_agg.items():
        gap_qty = agg["pending"]
        gap_pct = round((gap_qty / agg["ordered"] * 100) if agg["ordered"] > 0 else 0, 1)
        if gap_qty > 0:
            material_gaps.append({
                "material": mat_key,
                "ordered": agg["ordered"],
                "delivered": agg["delivered"],
                "pending": gap_qty,
                "gap_pct": gap_pct,
            })
    material_gaps.sort(key=lambda x: x["pending"], reverse=True)

    # ── Vendor Risk (sorted by pending qty) ──
    vendor_risk = []
    for vendor_key, agg in vendor_agg.items():
        if agg["total_pending"] > 0 or agg["total_ordered"] > 0:
            vendor_risk.append({
                "vendor": vendor_key,
                "total_ordered": agg["total_ordered"],
                "total_pending": agg["total_pending"],
                "po_count": agg["po_count"],
                "fulfillment_pct": round(
                    ((agg["total_ordered"] - agg["total_pending"]) / agg["total_ordered"] * 100)
                    if agg["total_ordered"] > 0 else 0, 1
                ),
            })
    vendor_risk.sort(key=lambda x: x["total_pending"], reverse=True)

    return {
        "summary": {
            "total_po_count": len(po_records),
            "total_ordered_qty": total_ordered,
            "total_delivered_qty": total_delivered,
            "fulfillment_pct": fulfillment_pct,
            "total_pending_qty": total_pending,
            "consumed_qty": consumed_qty,
            "consumed_value_inr": consumed_value_inr,
            "inventory_qty": inventory_qty,
            "inventory_value_inr": inventory_value_inr,
            "supply_gap_qty": supply_gap,
        },
        "material_gaps": material_gaps[:10],  # top 10
        "vendor_risk": vendor_risk[:10],  # top 10
    }


# ═══════════════════════════════════════════════════════════
# 3. TRANSMISSION (TC) VARIANCE
# ═══════════════════════════════════════════════════════════

def _parse_pct(value) -> float:
    """Parse a percentage string like '65%' or '65' to a float."""
    if value is None:
        return 0.0
    s = str(value).strip().replace('%', '')
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _parse_date_str(value) -> date | None:
    """Parse a date string in common formats."""
    if not value or str(value).strip() == '':
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def compute_tc_variance(db: Session, project_id: str) -> dict:
    """
    Compute transmission line variance from TC data.

    Data path: project_mapping.id → tc_project_entry.mapping_id → tc_network_edge
    
    For each edge: parse foundation/erection/stringing progress,
    compare expected_date to today, flag at-risk lines.
    
    NOTE: Currently returns empty — TC edges are 0 for mapped projects.
    The module is built so it activates when Transmission API data arrives.
    """
    from services.project_service import filter_tc_edges_by_kps

    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()

    empty_result = {
        "summary": {
            "total_lines": 0,
            "completed": 0,
            "in_progress": 0,
            "not_started": 0,
            "avg_foundation_pct": 0,
            "avg_erection_pct": 0,
            "avg_stringing_pct": 0,
        },
        "at_risk_lines": [],
    }

    if not mapping:
        return empty_result

    # Get TC project entries linked to this mapping
    project_entries = db.query(models.TcProjectEntry).filter(
        models.TcProjectEntry.mapping_id == mapping.id
    ).all()

    # Get TC edges via phase matching + KPS filtering (reuse existing logic)
    phases = set(str(pe.phase).strip().upper() for pe in project_entries if pe.phase)

    tc_edges = []
    if phases:
        all_edges = db.query(models.TcNetworkEdge).all()
        filtered = []
        for edge in all_edges:
            edge_phases = set()
            if edge.projects:
                try:
                    parsed = json.loads(edge.projects)
                    if isinstance(parsed, dict):
                        edge_phases = set(str(p).strip().upper() for p in parsed.get("phases", []))
                except Exception:
                    pass
            if phases.intersection(edge_phases):
                filtered.append(edge)
        tc_edges = filter_tc_edges_by_kps(filtered, project_entries)

    # Also include direct mappings
    direct_edges = db.query(models.TcNetworkEdge).filter(
        models.TcNetworkEdge.mapping_id == mapping.id
    ).all()
    tc_edges.extend(direct_edges)
    tc_edges = list({e.id: e for e in tc_edges}.values())

    if not tc_edges:
        return empty_result

    today = date.today()
    total_foundation = []
    total_erection = []
    total_stringing = []
    completed = 0
    in_progress = 0
    not_started = 0
    at_risk_lines = []

    for edge in tc_edges:
        f_pct = _parse_pct(edge.foundation)
        e_pct = _parse_pct(edge.erection)
        s_pct = _parse_pct(edge.stringing)
        avg_progress = (f_pct + e_pct + s_pct) / 3

        total_foundation.append(f_pct)
        total_erection.append(e_pct)
        total_stringing.append(s_pct)

        # Status classification
        status_lower = (edge.normalized_status or edge.status or "").lower()
        if "completed" in status_lower or "commissioned" in status_lower:
            completed += 1
        elif avg_progress > 0:
            in_progress += 1
        else:
            not_started += 1

        # At-risk detection
        exp_date = _parse_date_str(edge.expected_date)
        days_remaining = (exp_date - today).days if exp_date else None

        if days_remaining is not None and days_remaining < 60 and avg_progress < 50:
            at_risk_lines.append({
                "edge_id": edge.edge_id,
                "from_label": edge.from_label,
                "to_label": edge.to_label,
                "expected_date": _safe_date_str(exp_date),
                "days_remaining": days_remaining,
                "foundation_pct": f_pct,
                "erection_pct": e_pct,
                "stringing_pct": s_pct,
                "contractor": edge.contractor,
                "status": edge.status,
            })

    at_risk_lines.sort(key=lambda x: x["days_remaining"])

    return {
        "summary": {
            "total_lines": len(tc_edges),
            "completed": completed,
            "in_progress": in_progress,
            "not_started": not_started,
            "avg_foundation_pct": round(sum(total_foundation) / len(total_foundation), 1) if total_foundation else 0,
            "avg_erection_pct": round(sum(total_erection) / len(total_erection), 1) if total_erection else 0,
            "avg_stringing_pct": round(sum(total_stringing) / len(total_stringing), 1) if total_stringing else 0,
        },
        "at_risk_lines": at_risk_lines[:10],
    }


# ═══════════════════════════════════════════════════════════
# 4. FULL VARIANCE ORCHESTRATOR
# ═══════════════════════════════════════════════════════════

def compute_full_variance(db: Session, project_name_or_id: str) -> dict:
    """
    Orchestrator: calls all three variance sub-engines and merges results.
    
    Also computes cross-domain correlations:
    - If SAP has a supply gap AND the same construction phase is drifting in P6
      → flag as "compounding risk"
    
    Args:
        project_name_or_id: Either a project_id (e.g., 'FY26-P04') or a project name.
                           We try project_id first, then fall back to name matching.
    """
    # Resolve project_id from name if needed
    project_id = _resolve_project_id(db, project_name_or_id)

    if not project_id:
        logger.warning(f"Could not resolve project: {project_name_or_id}")
        return {
            "p6": compute_p6_variance(db, ""),
            "sap": compute_sap_variance(db, ""),
            "tc": compute_tc_variance(db, ""),
            "schedule_impact": [0, 0, 0],
            "cross_domain_risks": [],
            "engine_version": "2.0",
        }

    p6 = compute_p6_variance(db, project_id)
    sap = compute_sap_variance(db, project_id)
    tc = compute_tc_variance(db, project_id)

    # ── Cross-domain risk detection ──
    cross_domain_risks = []

    # If SAP supply gap > 0 AND P6 shows drift in related phases
    if sap["summary"]["supply_gap_qty"] > 0:
        drifting_phases = [
            pv["phase"] for pv in p6["phase_variance"]
            if pv["avg_drift_days"] > 14  # more than 2 weeks drift
        ]
        if drifting_phases:
            cross_domain_risks.append({
                "type": "compounding_risk",
                "description": (
                    f"Supply gap of {sap['summary']['supply_gap_qty']:,.0f} units "
                    f"coincides with schedule drift in: {', '.join(drifting_phases)}. "
                    f"Material shortage may be causing or amplifying construction delays."
                ),
                "severity": "Critical" if sap["summary"]["supply_gap_qty"] > 1000 else "Warning",
                "sap_gap_qty": sap["summary"]["supply_gap_qty"],
                "drifting_phases": drifting_phases,
            })

    # If TC lines are at risk AND P6 commissioning is drifting
    if tc["at_risk_lines"]:
        comm_phase = next(
            (pv for pv in p6["phase_variance"] if pv["phase"] == "Commissioning"),
            None
        )
        if comm_phase and comm_phase["avg_drift_days"] > 14:
            cross_domain_risks.append({
                "type": "transmission_bottleneck",
                "description": (
                    f"{len(tc['at_risk_lines'])} transmission lines at risk "
                    f"while commissioning phase shows {comm_phase['avg_drift_days']}d avg drift. "
                    f"Grid connection timeline may be doubly constrained."
                ),
                "severity": "Critical",
                "at_risk_line_count": len(tc["at_risk_lines"]),
                "commissioning_drift_days": comm_phase["avg_drift_days"],
            })

    return {
        "p6": p6,
        "sap": sap,
        "tc": tc,
        "schedule_impact": p6["schedule_impact"],
        "cross_domain_risks": cross_domain_risks,
        "engine_version": "2.0",
    }


def _resolve_project_id(db: Session, name_or_id: str) -> str | None:
    """Resolve a project name or ID to a valid project_id from project_mapping."""
    if not name_or_id or name_or_id == "Entire Portfolio":
        return None

    # Try direct project_id match first
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == name_or_id
    ).first()
    if mapping:
        return mapping.project_id

    # Try matching against P6 project name
    p6 = db.query(models.P6Project).filter(
        models.P6Project.name == name_or_id
    ).first()
    if p6:
        mapping = db.query(models.ProjectMapping).filter(
            models.ProjectMapping.project_id == p6.project_id
        ).first()
        if mapping:
            return mapping.project_id

    # Try matching against project_mapping.project field
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project == name_or_id
    ).first()
    if mapping and mapping.project_id:
        return mapping.project_id

    # Try matching against project_mapping.project_name_from_p6
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_name_from_p6 == name_or_id
    ).first()
    if mapping and mapping.project_id:
        return mapping.project_id

    return None


# ═══════════════════════════════════════════════════════════
# PORTFOLIO VARIANCE (for "All Projects" mode)
# ═══════════════════════════════════════════════════════════

def compute_portfolio_variance(db: Session, top_n: int = 10) -> dict:
    """
    Compute aggregate variance across the top-N riskiest mapped projects.
    
    Uses the existing project_360 risk scoring to pick the worst projects,
    then runs compute_p6_variance on each and aggregates.
    """
    from services.project_service import calculate_project_360_metrics

    all_projects = calculate_project_360_metrics(db)
    # Take the top_n riskiest
    top_projects = sorted(all_projects, key=lambda x: (x.get("delayDays", 0) or 0), reverse=True)[:top_n]

    aggregate_phase_drift = defaultdict(list)
    total_activities = 0
    total_drifted = 0
    total_critical = 0
    all_top_drifters = []

    for proj in top_projects:
        pid = proj.get("projectId")
        if not pid:
            continue
        p6_var = compute_p6_variance(db, pid)
        total_activities += p6_var["summary"]["total_activities"]
        total_drifted += p6_var["summary"]["drifted_activities"]
        total_critical += p6_var["summary"]["critical_activities"]

        for pv in p6_var["phase_variance"]:
            aggregate_phase_drift[pv["phase"]].append(pv["avg_drift_days"])

        for d in p6_var["top_drifters"][:3]:
            d["project_name"] = proj["projectName"]
            all_top_drifters.append(d)

    # Aggregate phase variance
    phase_variance = []
    for phase, drifts in sorted(aggregate_phase_drift.items()):
        phase_variance.append({
            "phase": phase,
            "avg_drift_days": round(sum(drifts) / len(drifts), 1) if drifts else 0,
            "max_drift_days": max(drifts) if drifts else 0,
            "project_count": len(drifts),
        })
    phase_variance.sort(key=lambda x: x["avg_drift_days"], reverse=True)

    phase_drift_map = {pv["phase"]: pv["avg_drift_days"] for pv in phase_variance}
    schedule_impact = [
        round(phase_drift_map.get("Foundation", 0)),
        round(phase_drift_map.get("Module Installation", 0)),
        round(phase_drift_map.get("Commissioning", 0)),
    ]

    all_top_drifters.sort(key=lambda x: x["drift_days"], reverse=True)

    return {
        "p6": {
            "project_id": "PORTFOLIO",
            "project_name": f"Top {top_n} Riskiest Projects",
            "data_date": _safe_date_str(date.today()),
            "summary": {
                "total_activities": total_activities,
                "baselined_activities": total_activities,
                "drifted_activities": total_drifted,
                "critical_activities": total_critical,
                "avg_finish_drift_days": 0,
                "max_finish_drift_days": 0,
            },
            "phase_variance": phase_variance,
            "schedule_impact": schedule_impact,
            "top_drifters": all_top_drifters[:10],
        },
        "sap": compute_sap_variance(db, ""),
        "tc": compute_tc_variance(db, ""),
        "schedule_impact": schedule_impact,
        "cross_domain_risks": [],
        "engine_version": "2.0",
    }
