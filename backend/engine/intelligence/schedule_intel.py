"""
Akasha Intelligence Engine — Schedule Intelligence

Analyzes P6 activity data to produce:
- Delay waterfall (contribution of each phase to total delay)
- Block-level hotspot identification
- Critical path narrative
- Delay trend analysis
- Schedule-specific insights and next steps

Read-only: never modifies existing data.
"""

import logging
from datetime import datetime, date
from collections import defaultdict
from sqlalchemy.orm import Session

import models
from engine.variance import _classify_phase, _safe_date_str

logger = logging.getLogger(__name__)


def analyze_schedule(db: Session, ctx: dict) -> dict:
    """Full schedule intelligence analysis for a project."""
    p6_proj = ctx.get("p6_project")
    activities = ctx.get("activities", [])
    project_name = ctx["project_name"]

    if not p6_proj or not activities:
        return {
            "has_data": False,
            "health_score": None,
            "insights": [{
                "severity": "info",
                "domain": "schedule",
                "title": f"No P6 schedule data for {project_name}",
                "description": "Project has no activities loaded from Primavera P6.",
                "impact": "Cannot assess schedule health",
            }],
            "next_steps": [],
        }

    now = datetime.utcnow()
    data_date = p6_proj.data_date or p6_proj.last_synced_at or now

    # ═══════════════════════════════════════════════════════
    # 1. ACTIVITY-LEVEL ANALYSIS
    # ═══════════════════════════════════════════════════════
    total = len(activities)
    completed = [a for a in activities if a.status and 'complet' in a.status.lower()]
    in_progress = [a for a in activities if a.status and 'progress' in a.status.lower()]
    not_started = [a for a in activities if a.status and 'not started' in a.status.lower()]

    progress_pct = round(len(completed) / max(total, 1) * 100, 1)

    # ═══════════════════════════════════════════════════════
    # 2. PROJECT-LEVEL DELAY
    # ═══════════════════════════════════════════════════════
    total_delay_days = 0
    if p6_proj.baseline_finish_date and p6_proj.finish_date:
        total_delay_days = max(0, (p6_proj.finish_date - p6_proj.baseline_finish_date).days)

    # ═══════════════════════════════════════════════════════
    # 3. PHASE-LEVEL WATERFALL (delay breakdown by phase)
    # ═══════════════════════════════════════════════════════
    phase_data = defaultdict(lambda: {
        "total": 0, "completed": 0, "in_progress": 0, "behind": 0,
        "critical": 0, "drift_days": [], "worst_activities": [],
    })

    for act in activities:
        phase = _classify_phase(act.name)
        pd = phase_data[phase]
        pd["total"] += 1

        if act.status and 'complet' in act.status.lower():
            pd["completed"] += 1
        elif act.status and 'progress' in act.status.lower():
            pd["in_progress"] += 1

        if act.total_float is not None and act.total_float <= 0:
            pd["critical"] += 1

        # Compute drift
        if act.finish_date and act.baseline_finish_date:
            drift = (act.finish_date - act.baseline_finish_date).days
            if drift > 0:
                pd["behind"] += 1
                pd["drift_days"].append(drift)
                pd["worst_activities"].append({
                    "activity_id": act.activity_id,
                    "name": act.name,
                    "drift_days": drift,
                    "status": act.status,
                    "percent_complete": act.percent_complete,
                    "wbs_name": act.wbs_name,
                })

    # Build waterfall
    waterfall = []
    for phase_name, pd in sorted(phase_data.items()):
        avg_drift = round(sum(pd["drift_days"]) / max(len(pd["drift_days"]), 1), 1)
        max_drift = max(pd["drift_days"]) if pd["drift_days"] else 0
        phase_progress = round(pd["completed"] / max(pd["total"], 1) * 100, 1)

        # Sort worst activities by drift
        pd["worst_activities"].sort(key=lambda x: x["drift_days"], reverse=True)

        waterfall.append({
            "phase": phase_name,
            "total_activities": pd["total"],
            "completed": pd["completed"],
            "in_progress": pd["in_progress"],
            "behind_schedule": pd["behind"],
            "critical_count": pd["critical"],
            "progress_pct": phase_progress,
            "avg_drift_days": avg_drift,
            "max_drift_days": max_drift,
            "contribution_days": round(avg_drift * pd["behind"] / max(total, 1), 1),
            "top_3_worst": pd["worst_activities"][:3],
        })

    # Sort waterfall by worst phase first
    waterfall.sort(key=lambda x: x["avg_drift_days"], reverse=True)

    # ═══════════════════════════════════════════════════════
    # 4. BLOCK-LEVEL HOTSPOT ANALYSIS
    # ═══════════════════════════════════════════════════════
    block_data = defaultdict(lambda: {"total": 0, "behind": 0, "drift_days": [], "critical": 0})
    for act in activities:
        block = act.wbs_name or "Unknown"
        bd = block_data[block]
        bd["total"] += 1
        if act.total_float is not None and act.total_float <= 0:
            bd["critical"] += 1
        if act.finish_date and act.baseline_finish_date:
            drift = (act.finish_date - act.baseline_finish_date).days
            if drift > 0:
                bd["behind"] += 1
                bd["drift_days"].append(drift)

    block_hotspots = []
    for block_name, bd in block_data.items():
        if bd["behind"] > 0:
            avg_drift = round(sum(bd["drift_days"]) / max(len(bd["drift_days"]), 1), 1)
            block_hotspots.append({
                "block": block_name,
                "total_activities": bd["total"],
                "behind_count": bd["behind"],
                "critical_count": bd["critical"],
                "avg_drift_days": avg_drift,
                "max_drift_days": max(bd["drift_days"]) if bd["drift_days"] else 0,
            })
    block_hotspots.sort(key=lambda x: x["avg_drift_days"], reverse=True)

    # ═══════════════════════════════════════════════════════
    # 5. CRITICAL PATH ANALYSIS
    # ═══════════════════════════════════════════════════════
    critical_activities = [a for a in activities if a.total_float is not None and a.total_float <= 0]
    critical_behind = [
        a for a in critical_activities
        if a.finish_date and a.baseline_finish_date and (a.finish_date - a.baseline_finish_date).days > 0
    ]

    critical_path_summary = {
        "total_critical": len(critical_activities),
        "critical_behind": len(critical_behind),
        "critical_on_track": len(critical_activities) - len(critical_behind),
        "worst_critical": [
            {
                "activity_id": a.activity_id,
                "name": a.name,
                "drift_days": (a.finish_date - a.baseline_finish_date).days,
                "percent_complete": a.percent_complete,
                "wbs_name": a.wbs_name,
                "phase": _classify_phase(a.name),
            }
            for a in sorted(
                critical_behind,
                key=lambda x: (x.finish_date - x.baseline_finish_date).days,
                reverse=True
            )[:5]
        ],
    }

    # ═══════════════════════════════════════════════════════
    # 6. MILESTONE TRACKING
    # ═══════════════════════════════════════════════════════
    milestones = [
        a for a in activities
        if a.type and 'milestone' in a.type.lower()
    ]
    milestone_tracking = []
    for m in milestones:
        drift = None
        if m.finish_date and m.baseline_finish_date:
            drift = (m.finish_date - m.baseline_finish_date).days
        milestone_tracking.append({
            "name": m.name,
            "baseline_date": _safe_date_str(m.baseline_finish_date),
            "forecast_date": _safe_date_str(m.finish_date),
            "actual_date": _safe_date_str(m.actual_finish_date),
            "drift_days": drift,
            "status": m.status,
            "percent_complete": m.percent_complete,
        })

    # ═══════════════════════════════════════════════════════
    # 7. HEALTH SCORE COMPUTATION
    # ═══════════════════════════════════════════════════════
    # Schedule health: weighted blend of progress alignment, delay severity, critical path status
    planned_done = [a for a in activities if a.baseline_finish_date and a.baseline_finish_date <= data_date]
    planned_pct = round(len(planned_done) / max(total, 1) * 100, 1) if planned_done else 0
    spi_proxy = (progress_pct / planned_pct) if planned_pct > 0 else 1.0

    # Health score formula
    delay_penalty = min(total_delay_days * 0.5, 50)  # max 50 points penalty
    spi_score = min(max(spi_proxy * 50, 0), 50)  # 0-50 range
    critical_penalty = min(len(critical_behind) * 2, 20)  # max 20 penalty
    health_score = round(max(0, min(100, spi_score + 50 - delay_penalty - critical_penalty)), 1)

    # ═══════════════════════════════════════════════════════
    # 8. GENERATE INSIGHTS
    # ═══════════════════════════════════════════════════════
    insights = []

    # Insight: Overall delay
    if total_delay_days > 0:
        severity = "critical" if total_delay_days > 60 else "high" if total_delay_days > 30 else "medium"
        insights.append({
            "severity": severity,
            "domain": "schedule",
            "title": f"Project is {total_delay_days} days behind schedule",
            "description": f"Baseline finish: {_safe_date_str(p6_proj.baseline_finish_date)}, "
                          f"Forecast finish: {_safe_date_str(p6_proj.finish_date)}",
            "impact": f"COD delayed by approximately {total_delay_days} days",
            "evidence": {
                "baseline_finish": _safe_date_str(p6_proj.baseline_finish_date),
                "forecast_finish": _safe_date_str(p6_proj.finish_date),
            },
        })

    # Insight: Worst phase
    if waterfall and waterfall[0]["avg_drift_days"] > 7:
        worst = waterfall[0]
        insights.append({
            "severity": "high" if worst["avg_drift_days"] > 30 else "medium",
            "domain": "schedule",
            "title": f"{worst['phase']} phase is the biggest bottleneck ({worst['avg_drift_days']} days avg drift)",
            "description": f"{worst['behind_schedule']} of {worst['total_activities']} activities behind schedule. "
                          f"Worst activity: {worst['top_3_worst'][0]['name'] if worst['top_3_worst'] else 'N/A'} "
                          f"({worst['top_3_worst'][0]['drift_days'] if worst['top_3_worst'] else 0} days behind)",
            "impact": f"Phase contributing approximately {worst['contribution_days']} days to overall delay",
        })

    # Insight: Block hotspot
    if block_hotspots and block_hotspots[0]["avg_drift_days"] > 14:
        worst_block = block_hotspots[0]
        insights.append({
            "severity": "high",
            "domain": "schedule",
            "title": f"Block '{worst_block['block']}' is the worst performing block",
            "description": f"{worst_block['behind_count']} activities behind schedule, "
                          f"avg {worst_block['avg_drift_days']} days drift, "
                          f"{worst_block['critical_count']} on critical path",
            "impact": "Focus recovery efforts on this block",
        })

    # Insight: Critical path at risk
    if len(critical_behind) > 0:
        insights.append({
            "severity": "critical" if len(critical_behind) > 5 else "high",
            "domain": "schedule",
            "title": f"{len(critical_behind)} critical path activities are behind schedule",
            "description": f"Out of {len(critical_activities)} total critical activities. "
                          f"Delays on critical path directly extend the project finish date.",
            "impact": "Every day of delay on critical path = 1 day delay on COD",
        })

    # Insight: Low progress
    if progress_pct < planned_pct - 10:
        gap = round(planned_pct - progress_pct, 1)
        insights.append({
            "severity": "high",
            "domain": "schedule",
            "title": f"Progress is {gap}% behind where it should be",
            "description": f"Actual progress: {progress_pct}%, Expected by now: {planned_pct}% "
                          f"(based on baseline schedule)",
            "impact": f"SPI proxy: {round(spi_proxy, 2)} — project is earning slower than planned",
        })

    # ═══════════════════════════════════════════════════════
    # 9. GENERATE NEXT STEPS
    # ═══════════════════════════════════════════════════════
    next_steps = []

    if total_delay_days > 30 and waterfall:
        worst_phase = waterfall[0]
        next_steps.append({
            "priority": "P1",
            "category": "construction",
            "action": f"Crash {worst_phase['phase']} activities — add second crew or parallel sequencing",
            "reason": f"{worst_phase['phase']} is the primary delay driver with {worst_phase['avg_drift_days']} days avg drift",
            "assigned_role": "site_pm",
        })

    if block_hotspots and block_hotspots[0]["avg_drift_days"] > 20:
        worst_block = block_hotspots[0]
        next_steps.append({
            "priority": "P1",
            "category": "construction",
            "action": f"Deploy additional resources to block '{worst_block['block']}' to recover {worst_block['avg_drift_days']} days",
            "reason": f"This block has {worst_block['behind_count']} delayed activities and is dragging the project",
            "assigned_role": "site_pm",
        })

    if len(critical_behind) > 3:
        next_steps.append({
            "priority": "P1",
            "category": "planning",
            "action": f"Conduct critical path review — {len(critical_behind)} critical activities are slipping",
            "reason": "Critical path delays directly extend COD",
            "assigned_role": "pmag",
        })

    if total_delay_days > 60:
        next_steps.append({
            "priority": "P2",
            "category": "planning",
            "action": "Evaluate re-baselining the project schedule with realistic dates",
            "reason": f"Project is {total_delay_days} days behind — recovery may not be feasible with current baseline",
            "assigned_role": "pmag",
        })

    return {
        "has_data": True,
        "health_score": health_score,
        "total_delay_days": total_delay_days,

        # Summary metrics
        "summary": {
            "total_activities": total,
            "completed": len(completed),
            "in_progress": len(in_progress),
            "not_started": len(not_started),
            "progress_pct": progress_pct,
            "planned_pct": planned_pct,
            "spi_proxy": round(spi_proxy, 2),
            "data_date": _safe_date_str(data_date),
            "baseline_finish": _safe_date_str(p6_proj.baseline_finish_date),
            "forecast_finish": _safe_date_str(p6_proj.finish_date),
        },

        # Detailed breakdowns
        "delay_waterfall": waterfall,
        "block_hotspots": block_hotspots[:10],
        "critical_path": critical_path_summary,
        "milestones": milestone_tracking,

        # Intelligence outputs
        "insights": insights,
        "next_steps": next_steps,
    }
