"""
Akasha Intelligence Engine — Predictive Intelligence

Generates forward-looking predictions and early warnings:
- Material shortfall forecasting
- Schedule milestone risk prediction
- Vendor reliability predictions
- Early warning signals
- Benchmark comparisons against portfolio

Read-only: never modifies existing data.
"""

import logging
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from engine.variance import _classify_phase

logger = logging.getLogger(__name__)


def generate_predictions(db: Session, ctx: dict,
                         schedule: dict, materials: dict,
                         transmission: dict) -> dict:
    """Generate forward-looking predictions and early warnings."""
    project_name = ctx["project_name"]
    p6_proj = ctx.get("p6_project")
    activities = ctx.get("activities", [])

    early_warnings = []
    forecasts = []

    # ═══════════════════════════════════════════════════════
    # 1. SCHEDULE MILESTONE RISK (upcoming milestones at risk)
    # ═══════════════════════════════════════════════════════
    if activities:
        now = datetime.utcnow()
        lookahead_30 = now + timedelta(days=30)
        lookahead_60 = now + timedelta(days=60)

        # Activities due in next 30 days that are behind
        upcoming_at_risk = []
        for act in activities:
            if (act.planned_finish_date and act.planned_finish_date <= lookahead_30
                and act.status and 'complet' not in act.status.lower()):

                pct = act.percent_complete or 0
                if pct < 70:  # Due in 30 days but less than 70% complete
                    drift = 0
                    if act.finish_date and act.baseline_finish_date:
                        drift = (act.finish_date - act.baseline_finish_date).days

                    upcoming_at_risk.append({
                        "activity_id": act.activity_id,
                        "name": act.name,
                        "planned_finish": act.planned_finish_date.isoformat(),
                        "percent_complete": pct,
                        "drift_days": drift,
                        "days_remaining": (act.planned_finish_date - now).days,
                        "is_critical": act.total_float is not None and act.total_float <= 0,
                        "phase": _classify_phase(act.name),
                    })

        if upcoming_at_risk:
            critical_at_risk = [a for a in upcoming_at_risk if a["is_critical"]]
            early_warnings.append({
                "type": "milestone_risk",
                "severity": "critical" if critical_at_risk else "high",
                "title": f"{len(upcoming_at_risk)} activities due in 30 days are at risk of missing deadline",
                "description": f"{len(critical_at_risk)} of these are on the critical path. "
                              f"Worst: '{upcoming_at_risk[0]['name']}' — "
                              f"only {upcoming_at_risk[0]['percent_complete']}% complete, "
                              f"due in {upcoming_at_risk[0]['days_remaining']} days",
                "details": upcoming_at_risk[:10],
            })

    # ═══════════════════════════════════════════════════════
    # 2. MATERIAL SHORTFALL PREDICTION
    # ═══════════════════════════════════════════════════════
    material_summary = materials.get("summary", {})
    if material_summary.get("total_ordered_qty", 0) > 0:
        ordered = material_summary.get("total_ordered_qty", 0)
        delivered = material_summary.get("total_delivered_qty", 0)
        pending = material_summary.get("total_pending_qty", 0)
        inventory = material_summary.get("total_inventory_qty", 0)

        # If more than 30% still pending, flag it
        pending_pct = pending / max(ordered, 1) * 100
        if pending_pct > 30:
            early_warnings.append({
                "type": "material_shortfall",
                "severity": "high" if pending_pct > 50 else "medium",
                "title": f"{round(pending_pct)}% of ordered materials still pending delivery",
                "description": f"Ordered: {round(ordered):,}, Delivered: {round(delivered):,}, "
                              f"Pending: {round(pending):,}. Current inventory: {round(inventory):,} units. "
                              f"If delivery pace doesn't improve, construction will stall.",
                "forecast": {
                    "current_fulfillment_pct": round(100 - pending_pct, 1),
                    "at_risk": pending_pct > 50,
                },
            })

    # Overdue PO impact forecast
    overdue_pos = materials.get("overdue_pos", [])
    if overdue_pos:
        total_overdue_days = sum(po.get("days_overdue", 0) for po in overdue_pos)
        avg_overdue = round(total_overdue_days / len(overdue_pos), 1)
        early_warnings.append({
            "type": "procurement_delay",
            "severity": "high",
            "title": f"{len(overdue_pos)} POs averaging {avg_overdue} days overdue — construction likely blocked",
            "description": f"If these POs are for critical materials (modules, cables, transformers), "
                          f"expect schedule slippage of approximately {avg_overdue} days on dependent activities.",
        })

    # ═══════════════════════════════════════════════════════
    # 3. TRANSMISSION COD FORECAST
    # ═══════════════════════════════════════════════════════
    tc_summary = transmission.get("summary", {})
    if tc_summary.get("is_tc_binding_constraint"):
        early_warnings.append({
            "type": "cod_at_risk",
            "severity": "critical",
            "title": "COD is constrained by transmission — not construction",
            "description": f"Even with full schedule recovery, COD will be delayed by "
                          f"~{tc_summary.get('tc_extends_cod_by_days', 0)} days due to transmission line readiness. "
                          f"All construction acceleration is futile unless transmission is also accelerated.",
        })

    # ═══════════════════════════════════════════════════════
    # 4. PORTFOLIO BENCHMARK (compare to peers)
    # ═══════════════════════════════════════════════════════
    if p6_proj and activities:
        # Get average progress of all projects in same category
        category = ctx.get("category")
        if category:
            peer_projects = db.query(
                func.avg(models.P6Project.duration_percent_complete)
            ).join(
                models.ProjectMapping,
                models.ProjectMapping.project_id == models.P6Project.project_id
            ).filter(
                models.ProjectMapping.category == category,
                models.P6Project.project_id != ctx["project_id"],
            ).scalar()

            if peer_projects and peer_projects > 0:
                my_progress = p6_proj.duration_percent_complete or 0
                peer_avg = round(float(peer_projects), 1)
                gap = round(my_progress - peer_avg, 1)

                forecasts.append({
                    "type": "benchmark",
                    "title": f"Progress comparison vs {category} peers",
                    "my_progress": round(my_progress, 1),
                    "peer_average": peer_avg,
                    "gap": gap,
                    "status": "AHEAD" if gap > 5 else "BEHIND" if gap < -5 else "ON_PAR",
                    "description": (
                        f"This project is at {round(my_progress, 1)}% progress vs "
                        f"{peer_avg}% average for {category} projects. "
                        + (f"**{abs(gap)}% behind peers.**" if gap < -5 else
                           f"**{gap}% ahead of peers.**" if gap > 5 else
                           "On par with peers.")
                    ),
                })

    # ═══════════════════════════════════════════════════════
    # 5. DELAY TRAJECTORY (is delay growing?)
    # ═══════════════════════════════════════════════════════
    if schedule.get("total_delay_days", 0) > 15 and p6_proj:
        # We can infer trend from data_date progression if available
        total_delay = schedule["total_delay_days"]
        early_warnings.append({
            "type": "delay_trajectory",
            "severity": "high" if total_delay > 45 else "medium",
            "title": f"Project is {total_delay} days behind schedule",
            "description": f"Monitor whether delay is stabilizing or growing. "
                          f"If growing, consider re-baselining the schedule. "
                          f"If stable, recovery plan may still be viable.",
            "recommendation": (
                "Consider re-baselining" if total_delay > 60 else
                "Deploy recovery plan with additional resources" if total_delay > 30 else
                "Monitor closely, implement corrective actions"
            ),
        })

    return {
        "early_warnings": early_warnings,
        "forecasts": forecasts,
        "warning_count": len(early_warnings),
        "critical_warnings": len([w for w in early_warnings if w.get("severity") == "critical"]),
    }
