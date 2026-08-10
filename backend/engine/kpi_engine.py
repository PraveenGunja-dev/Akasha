"""
Akasha KPI Engine

Computes project KPIs (progress, SPI, schedule variance, risk, health) using the
enterprise methodology — but derived from the PROJECT'S UNDERLYING DATA (P6 activities,
SAP POs, TC lines), NEVER from the stored summary columns. The stored
`schedule_performance_index`, `total_float`, and `duration_percent_complete` on
`p6_project` are null/unreliable in this database, so every KPI here is recomputed
from the activity-level truth.

Methodology (adapted to the data that actually exists):
- Physical / schedule progress  = completed activities / total activities.
- SPI (EV/PV proxy)             = actual progress % / planned progress % as of the data date,
                                   where planned % = share of activities whose BASELINE finish
                                   is on/before the data date (i.e. should be done by now).
- Schedule Variance (SV)        = actual progress % - planned progress % (negative = behind).
- Schedule risk                 = activities behind schedule / total activities.
- Procurement risk              = PO lines still pending delivery / total PO lines (SAP).
- Execution risk                = delayed transmission lines / total lines (TC; transmission only).
- Overall risk                  = 0.40*schedule + 0.30*procurement + 0.30*execution,
                                   RENORMALIZED over whichever components have data.
- Health score                  = weighted blend of SPI, progress and (100 - risk),
                                   renormalized over available KPIs; higher = healthier.

Any KPI whose data doesn't exist is returned as None with a reason, never faked. KPIs
that need data absent from this schema (DPC daily targets, manpower productivity, resource
utilization, HSE/safety) are intentionally not produced.
"""

import logging
from datetime import datetime
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)


def _is_complete(a) -> bool:
    return bool(a.status and 'complet' in a.status.lower())


def compute_schedule_kpis(p6, activities: list, as_of: datetime = None) -> dict:
    """Schedule KPIs for one project, computed purely from its activities."""
    as_of = as_of or p6.data_date or p6.last_synced_at or datetime.utcnow()
    total = len(activities)
    if total == 0:
        return {"has_data": False, "reason": "No activities for this project."}

    completed = [a for a in activities if _is_complete(a)]
    progress_pct = round(len(completed) / total * 100, 1)

    # Planned progress as-of the data date = share of activities that SHOULD be finished by now
    planned_done = [a for a in activities if a.baseline_finish_date and a.baseline_finish_date <= as_of]
    planned_pct = round(len(planned_done) / total * 100, 1)

    spi = round(progress_pct / planned_pct, 2) if planned_pct > 0 else None
    sv_pct = round(progress_pct - planned_pct, 1)  # earned - planned, in progress-% points

    # Activities behind schedule: incomplete AND their baseline finish has already passed
    behind = [a for a in activities if not _is_complete(a) and a.baseline_finish_date and a.baseline_finish_date < as_of]
    schedule_risk_pct = round(len(behind) / total * 100, 1)

    # Critical path (float <= 0 among activities that report float)
    with_float = [a for a in activities if a.total_float is not None]
    critical = [a for a in with_float if a.total_float <= 0]

    # Average slip of the drifting activities
    drifting = [a for a in activities if not _is_complete(a) and a.baseline_finish_date and a.finish_date
                and (a.finish_date - a.baseline_finish_date).days > 0]
    avg_slip = round(sum((a.finish_date - a.baseline_finish_date).days for a in drifting) / len(drifting), 0) if drifting else 0

    return {
        "has_data": True,
        "as_of": as_of.date().isoformat(),
        "total_activities": total,
        "completed_activities": len(completed),
        "progress_pct": progress_pct,              # physical/schedule progress
        "planned_pct": planned_pct,                # where the baseline says we should be
        "spi": spi,                                # >1 ahead, <1 behind
        "schedule_variance_pct": sv_pct,           # negative = behind schedule
        "schedule_risk_pct": schedule_risk_pct,    # activities behind / total
        "activities_behind": len(behind),
        "critical_activities": len(critical),
        "avg_slip_days": avg_slip,
        "schedule_status": (
            "BEHIND" if (spi is not None and spi < 0.95) else
            "AHEAD" if (spi is not None and spi > 1.05) else "ON TRACK"
        ) if spi is not None else "UNKNOWN",
    }


def compute_procurement_risk(pos: list) -> dict:
    """Procurement risk from SAP PO lines: pending deliveries / total lines."""
    total = len(pos)
    if total == 0:
        return {"has_data": False, "reason": "No SAP PO data mapped to this project."}
    pending = sum(1 for po in pos if (po.still_to_deliver_qty or 0) > 0)
    return {
        "has_data": True,
        "total_po_lines": total,
        "pending_po_lines": pending,
        "procurement_risk_pct": round(pending / total * 100, 1),
    }


def compute_execution_risk(total_lines: int, delayed_lines: int) -> dict:
    """Execution risk from TC transmission lines: delayed / total. Transmission-scoped."""
    if not total_lines:
        return {"has_data": False, "reason": "No transmission lines mapped to this project."}
    return {
        "has_data": True,
        "total_lines": total_lines,
        "delayed_lines": delayed_lines,
        "execution_risk_pct": round(delayed_lines / total_lines * 100, 1),
    }


def combine_risk(schedule_risk, procurement_risk, execution_risk) -> dict:
    """Overall risk = 0.40*schedule + 0.30*procurement + 0.30*execution, renormalized over
    whichever components actually have data (so a solar project with no TC lines isn't
    penalized to zero on a component it can't have)."""
    components = []
    if schedule_risk is not None:
        components.append(("schedule", schedule_risk, 0.40))
    if procurement_risk is not None:
        components.append(("procurement", procurement_risk, 0.30))
    if execution_risk is not None:
        components.append(("execution", execution_risk, 0.30))
    if not components:
        return {"overall_risk_pct": None, "basis": "no risk data"}
    total_w = sum(w for _, _, w in components)
    overall = sum(v * w for _, v, w in components) / total_w
    return {
        "overall_risk_pct": round(overall, 1),
        "components": {name: round(v, 1) for name, v, _ in components},
        "basis": " + ".join(f"{name} {round(w/total_w*100)}%" for name, _, w in components),
    }


def compute_health_score(spi, progress_pct, overall_risk_pct) -> dict:
    """Composite health (0-100, higher = healthier) from the KPIs that exist here:
    SPI, physical progress, and inverse risk. Weights renormalized over what's available."""
    parts = []
    if spi is not None:
        parts.append(("spi", min(spi / 1.0, 1.0) * 100, 0.45))     # SPI 1.0 = full marks
    if progress_pct is not None:
        parts.append(("progress", progress_pct, 0.25))
    if overall_risk_pct is not None:
        parts.append(("low_risk", 100 - overall_risk_pct, 0.30))
    if not parts:
        return {"health_score": None}
    total_w = sum(w for _, _, w in parts)
    score = sum(v * w for _, v, w in parts) / total_w
    return {
        "health_score": round(score, 1),
        "health_status": "CRITICAL" if score < 55 else "AT RISK" if score < 75 else "HEALTHY",
    }


def compute_project_kpis(db: Session, project_id: str, activities: list = None,
                         pos: list = None, tc_total: int = None, tc_delayed: int = None) -> dict:
    """Full KPI bundle for one project. Prefetched inputs may be passed for portfolio-scale use;
    otherwise they're queried here."""
    mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == project_id).first()
    if not mapping:
        from engine.tools.portfolio_tools import portfolio_resolve_project_id
        resolved = portfolio_resolve_project_id(db, project_id)
        if resolved and resolved.get("project_id"):
            project_id = resolved["project_id"]
            mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == project_id).first()

    p6 = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    if not p6 and mapping and mapping.spv_name:
        p6 = db.query(models.P6Project).filter(models.P6Project.name.ilike(f"%{mapping.spv_name}%")).first()

    if not mapping and not p6:
        return {"project_id": project_id, "error": "Project not found"}

    if p6:
        if activities is None:
            activities = db.query(models.P6Activity).filter(
                models.P6Activity.project_object_id == p6.p6_object_id
            ).all()
        sched = compute_schedule_kpis(p6, activities)
    else:
        sched = {
            "has_data": False,
            "reason": f"No Primavera P6 schedule file uploaded for this project (Registered capacity: {mapping.capacity_mwac if mapping else 'N/A'} MWac).",
            "progress_pct": 0.0,
            "total_activities": "Pending P6 Upload",
            "schedule_status": "Registered in Master Registry (Pre-Execution / Pending P6 Upload)"
        }

    # Procurement (SAP) — resolve via WBS like the SAP tools do
    if pos is None:
        from engine.tools.sap_tools import _resolve_sap_filter, _query_po_by_project
        pos = _query_po_by_project(db, _resolve_sap_filter(db, project_id))
    proc = compute_procurement_risk(pos)

    # Execution (TC)
    if tc_total is None:
        from engine.tools.tc_tools import tc_get_project_lines
        t = tc_get_project_lines(db, project_id)
        tc_total = t.get("total_lines", 0) if t.get("has_data") else 0
        tc_delayed = t.get("delayed", 0) if t.get("has_data") else 0
    execu = compute_execution_risk(tc_total or 0, tc_delayed or 0)

    risk = combine_risk(
        sched.get("schedule_risk_pct") if sched.get("has_data") else None,
        proc.get("procurement_risk_pct") if proc.get("has_data") else None,
        execu.get("execution_risk_pct") if execu.get("has_data") else None,
    )
    health = compute_health_score(
        sched.get("spi") if sched.get("has_data") else None,
        sched.get("progress_pct") if sched.get("has_data") else None,
        risk.get("overall_risk_pct"),
    )

    from engine.tools.portfolio_tools import get_project_display_name
    proj_name = get_project_display_name(db, project_id)
    capacity_mw = mapping.capacity_mwac if mapping else None
    spv = mapping.spv_name if mapping else None
    cluster = mapping.cluster if mapping else None

    return {
        "project_id": project_id,
        "project_name": proj_name,
        "spv_name": spv,
        "cluster": cluster,
        "capacity_mwac": capacity_mw,
        "schedule": sched,
        "procurement": proc,
        "execution": execu,
        "overall_risk": risk,
        "health": health,
        "_note": "KPIs computed from available project mapping, schedule, procurement, and transmission data.",
        "_source_tables": ["project_mapping", "p6_activity", "mt_poamount", "tc_network_edge"],
    }


def compute_portfolio_kpis(db: Session) -> list[dict]:
    """Compute KPIs for every mapped project efficiently (prefetch activities/PO/TC once).
    Returns a list sorted by overall risk descending (riskiest first)."""
    # Prefetch activities grouped by project object id (1 query)
    acts_by_proj = defaultdict(list)
    for a in db.query(models.P6Activity).all():
        acts_by_proj[a.project_object_id].append(a)

    # Prefetch PO lines grouped by wbs_element
    pos_by_wbs = defaultdict(list)
    for po in db.query(models.MTPOAmount).all():
        if po.wbs_element:
            pos_by_wbs[str(po.wbs_element).strip().lower()].append(po)

    # Prefetch TC delayed/total per mapping_id
    tc_by_mapping = defaultdict(lambda: {"total": 0, "delayed": 0})
    for e in db.query(models.TcNetworkEdge).all():
        if e.mapping_id:
            tc_by_mapping[e.mapping_id]["total"] += 1
            if e.is_delayed:
                tc_by_mapping[e.mapping_id]["delayed"] += 1

    mappings = db.query(models.ProjectMapping).all()
    p6_by_pid = {p.project_id: p for p in db.query(models.P6Project).all()}

    results = []
    for m in mappings:
        name_check = m.project_name_from_p6 or m.project or ""
        if "demo" in name_check.lower():
            continue
        p6 = p6_by_pid.get(m.project_id)
        if not p6:
            continue

        activities = acts_by_proj.get(p6.p6_object_id, [])
        # Match PO lines by module_wbs prefix
        wbs = (m.module_wbs or "").strip().lower()
        pos = []
        if wbs and wbs not in ("nan", "none", "null"):
            for k, lst in pos_by_wbs.items():
                if k.startswith(wbs):
                    pos.extend(lst)
        tc = tc_by_mapping.get(m.id, {"total": 0, "delayed": 0})

        kpi = compute_project_kpis(db, m.project_id, activities=activities, pos=pos,
                                   tc_total=tc["total"], tc_delayed=tc["delayed"])
        results.append(kpi)

    results.sort(key=lambda r: (r.get("overall_risk", {}).get("overall_risk_pct") or -1), reverse=True)
    return results
