"""
Akasha KPI Engine

Computes project schedule and risk facts from available P6, SAP, and TC data. Formula-derived
EVM and health metrics are added only for an explicit specific-project health request.

Methodology (adapted to the data that actually exists):
- Overall progress              = P6 SummaryDurationPercentComplete.
- Activity completion ratio     = completed activities / total activities (descriptive only).
- Earned value (EV)             = actual cost * P6 duration completion fraction.
- Planned value (PV / BCWS)     = P6 SummaryPlannedCost.
- SPI / CPI                     = EV / PV and EV / actual cost.
- Schedule / cost variance      = EV - PV and EV - actual cost.
- Baseline deadline exposure    = overdue incomplete activities / total activities.
- Procurement risk              = PO lines still pending delivery / total PO lines (SAP).
- Execution risk                = delayed transmission lines / total lines (TC; transmission only).
- Overall risk                  = 0.40*schedule + 0.30*procurement + 0.30*execution,
                                   RENORMALIZED over whichever components have data.
- Risk score                    = 1 - overall risk exposure fraction; higher = healthier.
- Health index                  = 0.40*SPI + 0.30*CPI + 0.30*risk score.

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


def _normalize_percentage(value) -> float | None:
    if value is None:
        return None
    percentage = float(value)
    if percentage <= 1.5:
        percentage *= 100
    return round(percentage, 1)


def compute_evm_metrics(actual_cost, progress_pct, planned_value) -> dict:
    """Calculate EVM using AC, duration completion, and BCWS/PV without fallbacks."""
    ac = float(actual_cost) if actual_cost is not None else None
    pv = float(planned_value) if planned_value is not None else None
    completion_pct = float(progress_pct) if progress_pct is not None else None
    if completion_pct is not None and completion_pct <= 1.5:
        completion_pct *= 100
    ev = ac * completion_pct / 100 if ac is not None and completion_pct is not None else None

    spi = ev / pv if ev is not None and pv is not None and pv > 0 else None
    cpi = ev / ac if ev is not None and ac is not None and ac > 0 else None
    sv = ev - pv if ev is not None and pv is not None else None
    cv = ev - ac if ev is not None and ac is not None else None

    limitations = []
    if ac is None:
        limitations.append("Actual Cost (AC) is unavailable.")
    elif ac <= 0:
        limitations.append("Actual Cost (AC) must be greater than zero to calculate CPI.")
    if completion_pct is None:
        limitations.append("P6 duration percentage complete is unavailable.")
    if pv is None:
        limitations.append("Planned Value (PV/BCWS) is unavailable.")
    elif pv <= 0:
        limitations.append("Planned Value (PV/BCWS) must be greater than zero to calculate SPI.")

    return {
        "actual_cost": round(ac, 2) if ac is not None else None,
        "percentage_complete": round(completion_pct, 4) if completion_pct is not None else None,
        "earned_value": round(ev, 2) if ev is not None else None,
        "planned_value": round(pv, 2) if pv is not None else None,
        "spi": round(spi, 4) if spi is not None else None,
        "cpi": round(cpi, 4) if cpi is not None else None,
        "schedule_variance": round(sv, 2) if sv is not None else None,
        "cost_variance": round(cv, 2) if cv is not None else None,
        "formula": {
            "ev": "AC * (Percentage Complete / 100)",
            "pv": "BCWS (P6 SummaryPlannedCost)",
            "spi": "EV / PV",
            "cpi": "EV / AC",
            "sv": "EV - PV",
            "cv": "EV - AC",
        },
        "limitations": limitations,
    }


def compute_schedule_kpis(p6, activities: list, as_of: datetime = None) -> dict:
    """General schedule facts for one project using native P6 performance indicators."""
    as_of = as_of or p6.data_date or p6.last_synced_at or datetime.utcnow()
    total = len(activities)

    completed = [a for a in activities if _is_complete(a)]
    in_progress = [a for a in activities if a.status and 'progress' in a.status.lower()]
    not_started = [a for a in activities if a.status and 'not started' in a.status.lower()]
    activity_completion_pct = round(len(completed) / total * 100, 1) if total else None
    progress_pct = _normalize_percentage(p6.duration_percent_complete)
    source_spi = getattr(p6, "schedule_performance_index", None)
    source_cpi = getattr(p6, "cost_performance_index", None)
    spi = round(float(source_spi), 4) if source_spi is not None else None
    cpi = round(float(source_cpi), 4) if source_cpi is not None else None

    # Activities behind schedule: incomplete AND their baseline finish has already passed
    behind = [a for a in activities if not _is_complete(a) and a.baseline_finish_date and a.baseline_finish_date < as_of]
    deadline_exposure_pct = round(len(behind) / total * 100, 1) if total else None

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
        "project_status": p6.status,
        "scheduled_finish": p6.scheduled_finish_date.isoformat() if p6.scheduled_finish_date else None,
        "data_date": p6.data_date.isoformat() if p6.data_date else None,
        "last_synced_at": p6.last_synced_at.isoformat() if p6.last_synced_at else None,
        "total_activities": total,
        "completed_activities": len(completed),
        "in_progress_activities": len(in_progress),
        "not_started_activities": len(not_started),
        "progress_pct": progress_pct,
        "progress_basis": "P6 SummaryDurationPercentComplete",
        "activity_completion_pct": activity_completion_pct,
        "planned_pct": None,
        "spi": spi,
        "cpi": cpi,
        "schedule_variance_pct": None,
        "performance_limitation": (
            "Native P6 SPI is unavailable; schedule performance cannot be classified from SPI."
            if spi is None else None
        ),
        "schedule_risk_pct": deadline_exposure_pct,
        "baseline_deadline_exposure_pct": deadline_exposure_pct,
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


def compute_health_score(spi, cpi, risk_score) -> dict:
    """Health = 0.40*SPI + 0.30*CPI + 0.30*risk score; no weight renormalization."""
    missing = [
        name for name, value in (("SPI", spi), ("CPI", cpi), ("Risk Score", risk_score))
        if value is None
    ]
    if missing:
        return {
            "health_score": None,
            "health_index": None,
            "health_status": "UNKNOWN",
            "reason": f"{', '.join(missing)} unavailable; all formula inputs are required.",
            "formula": "(SPI * 0.4) + (CPI * 0.3) + (Risk Score * 0.3)",
        }
    health_index = spi * 0.40 + cpi * 0.30 + risk_score * 0.30
    score = health_index * 100
    return {
        "health_score": round(score, 1),
        "health_index": round(health_index, 4),
        "health_status": "CRITICAL" if score < 55 else "AT RISK" if score < 75 else "HEALTHY",
        "components": {"spi": spi, "cpi": cpi, "risk_score": risk_score},
        "formula": "(SPI * 0.4) + (CPI * 0.3) + (Risk Score * 0.3)",
    }


def compute_project_kpis(db: Session, project_id: str, activities: list = None,
                         pos: list = None, tc_total: int = None, tc_delayed: int = None,
                         calculate_health: bool = False) -> dict:
    """Project exposure bundle; formula EVM and health require an explicit opt-in."""
    p6 = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    if not p6:
        return {"project_id": project_id, "error": "Project not found"}

    if activities is None:
        activities = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id
        ).all()

    sched = compute_schedule_kpis(p6, activities)

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
    health = None
    if calculate_health:
        evm = compute_evm_metrics(
            p6.actual_total_cost,
            p6.duration_percent_complete,
            p6.planned_cost,
        )
        source_spi = sched.get("spi")
        source_cpi = sched.get("cpi")
        sched.update({
            "spi": evm["spi"],
            "cpi": evm["cpi"],
            "source_spi": source_spi,
            "source_cpi": source_cpi,
            "actual_cost": evm["actual_cost"],
            "percentage_complete": evm["percentage_complete"],
            "earned_value": evm["earned_value"],
            "planned_value": evm["planned_value"],
            "schedule_variance": evm["schedule_variance"],
            "cost_variance": evm["cost_variance"],
            "evm_formula": evm["formula"],
            "performance_limitation": " ".join(evm["limitations"]) or None,
            "schedule_status": (
                "BEHIND" if evm["spi"] < 0.95 else
                "AHEAD" if evm["spi"] > 1.05 else "ON TRACK"
            ) if evm["spi"] is not None else "UNKNOWN",
        })
        overall_risk_pct = risk.get("overall_risk_pct")
        risk_score = (
            1 - max(0.0, min(overall_risk_pct, 100.0)) / 100
            if overall_risk_pct is not None else None
        )
        risk.update({
            "risk_score": round(risk_score, 4) if risk_score is not None else None,
            "risk_score_basis": "1 - (overall risk exposure / 100); 1.0 is lowest risk",
            "risk_score_method": "Derived exposure score; no manual subjective risk rating is stored.",
        })
        health = compute_health_score(evm["spi"], evm["cpi"], risk_score)

    from engine.tools.portfolio_tools import get_project_display_name
    result = {
        "project_id": project_id,
        "project_name": get_project_display_name(db, project_id),
        "schedule": sched,
        "procurement": proc,
        "execution": execu,
        "overall_risk": risk,
        "_note": "General schedule and risk data only; project health was not requested.",
        "_source_tables": ["p6_project", "p6_activity", "mt_poamount", "tc_network_edge"],
    }
    if calculate_health:
        result["health"] = health
        result["_note"] = "Specific-project health calculation requested. SPI, CPI, SV, and CV use the documented AC/completion/PV formulas; native P6 SPI/CPI are reconciliation fields."
    return result


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

        kpi = compute_project_kpis(
            db,
            m.project_id,
            activities=activities,
            pos=pos,
            tc_total=tc["total"],
            tc_delayed=tc["delayed"],
            calculate_health=False,
        )
        results.append(kpi)

    results.sort(key=lambda r: (r.get("overall_risk", {}).get("overall_risk_pct") or -1), reverse=True)
    return results
