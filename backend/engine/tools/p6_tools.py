"""
Akasha Tools Layer — P6 Schedule Data Tools

MCP-style tool functions that provide deterministic, read-only access
to Primavera P6 schedule data. These are the "hands" the agents use.

Naming convention: p6_* prefix on all tools (per MCP builder best practices).
"""

import logging
import re
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)


def _progress_percent(value) -> float | None:
    if value is None:
        return None
    pct = float(value)
    if 0 < pct <= 1:
        pct *= 100
    return round(pct, 1)


def _activity_percent(value) -> float | None:
    return _progress_percent(value)


def _activity_drift_days(activity) -> int | None:
    if not activity.finish_date or not activity.baseline_finish_date:
        return None
    return (activity.finish_date - activity.baseline_finish_date).days


def _activity_payload(activity, project_name: str) -> dict:
    drift = _activity_drift_days(activity)
    return {
        "activity_id": activity.activity_id,
        "name": activity.name,
        "status": activity.status,
        "total_float_hours": int(activity.total_float) if activity.total_float is not None else None,
        "percent_complete": _activity_percent(activity.percent_complete),
        "remaining_duration_hours": int(activity.remaining_duration) if activity.remaining_duration is not None else None,
        "start_date": activity.start_date.isoformat() if activity.start_date else None,
        "finish_date": activity.finish_date.isoformat() if activity.finish_date else None,
        "baseline_finish": activity.baseline_finish_date.isoformat() if activity.baseline_finish_date else None,
        "drift_days": drift,
        "is_delayed_vs_baseline": drift is not None and drift >= 7,
        "is_critical": activity.total_float is not None and activity.total_float <= 0,
        "wbs_name": activity.wbs_name,
        "project_name": project_name,
        "_source_table": "p6_activity",
    }


def _normalize_block_name(name: str) -> str:
    name = name.replace(" ", "").upper()
    match = re.match(r"(BLOCK-|WTG-?)0+(\d+)", name)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    return name


def _extract_block_name(value: str | None) -> str | None:
    match = re.search(r"(Block-\d+|WTG\s*\d+)", value or "", re.IGNORECASE)
    if not match:
        return None
    return _normalize_block_name(match.group(1))


def _days_between(later, earlier) -> int | None:
    if not later or not earlier:
        return None
    return (later.date() - earlier.date()).days


def _projected_finish(p6):
    return p6.scheduled_finish_date or p6.finish_date


def _schedule_status(p6, activities: list) -> dict:
    progress = _progress_percent(p6.duration_percent_complete)
    projected_finish = _projected_finish(p6)
    baseline_variance_days = _days_between(projected_finish, p6.baseline_finish_date)
    delayed_activity_drifts = [
        (a.finish_date - a.baseline_finish_date).days
        for a in activities
        if a.finish_date and a.baseline_finish_date and (a.finish_date - a.baseline_finish_date).days >= 7
    ]
    critical_count = sum(1 for a in activities if a.total_float is not None and a.total_float <= 0)

    if progress is not None and progress >= 100:
        status = "Complete"
        reason = "Project progress is at 100%."
    elif baseline_variance_days is not None and baseline_variance_days > 7:
        status = "Delayed"
        reason = f"Projected finish is {baseline_variance_days} days after the baseline finish."
    elif p6.finish_date_variance is not None and p6.finish_date_variance < -7:
        status = "Delayed"
        reason = f"Finish date variance is {int(p6.finish_date_variance)} hours."
    elif delayed_activity_drifts:
        status = "At Risk"
        reason = f"{len(delayed_activity_drifts)} activities are delayed by 7+ days."
    elif p6.total_float is not None and p6.total_float <= 0:
        status = "At Risk"
        reason = "Project has zero or negative total float."
    else:
        status = "On Track"
        reason = "No schedule delay indicators were found in the retrieved P6 summary."

    return {
        "schedule_status": status,
        "schedule_status_reason": reason,
        "progress_percent": progress,
        "projected_finish": projected_finish.isoformat() if projected_finish else None,
        "baseline_variance_days": baseline_variance_days,
        "delayed_activity_count": len(delayed_activity_drifts),
        "max_activity_drift_days": max(delayed_activity_drifts) if delayed_activity_drifts else 0,
        "critical_activity_count": critical_count,
    }


def p6_get_project_summary(db: Session, project_id: str) -> dict | None:
    """Get high-level project summary: dates, progress, SPI, CPI, activity counts.
    
    Use when: user asks about a specific project's overall status.
    Returns: dict with schedule, cost, and progress metrics, or None if not found.
    """
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    
    if not p6:
        return None
    
    from engine.tools.portfolio_tools import get_project_display_name
    project_name = get_project_display_name(db, project_id)
    
    # Dynamic activity counts from actual activity statuses
    activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id
    ).all()
    
    completed = sum(1 for a in activities if a.status and 'completed' in a.status.lower())
    in_progress = sum(1 for a in activities if a.status and 'progress' in a.status.lower())
    not_started = sum(1 for a in activities if a.status and 'not started' in a.status.lower())
    pending_statuses = {"not started", "in progress"}
    delayed_pending = sum(
        1 for a in activities
        if (a.status or "").strip().lower() in pending_statuses
        and (_activity_drift_days(a) or 0) >= 7
    )
    delayed_completed = sum(
        1 for a in activities
        if (a.status or "").strip().lower() == "completed"
        and (_activity_drift_days(a) or 0) >= 7
    )
    schedule = _schedule_status(p6, activities)
    
    return {
        "project_id": project_id,
        "project_name": project_name,
        "name": p6.name,
        "status": p6.status,
        "schedule_status": schedule["schedule_status"],
        "schedule_status_reason": schedule["schedule_status_reason"],
        "start_date": p6.start_date.isoformat() if p6.start_date else None,
        "finish_date": p6.finish_date.isoformat() if p6.finish_date else None,
        "projected_finish": schedule["projected_finish"],
        "planned_start": p6.planned_start_date.isoformat() if p6.planned_start_date else None,
        "scheduled_finish": p6.scheduled_finish_date.isoformat() if p6.scheduled_finish_date else None,
        "must_finish_by": p6.must_finish_by_date.isoformat() if p6.must_finish_by_date else None,
        "data_date": p6.data_date.isoformat() if p6.data_date else None,
        "progress_percent": schedule["progress_percent"],
        "duration_percent_complete": schedule["progress_percent"],
        "planned_duration": int(p6.planned_duration) if p6.planned_duration else None,
        "actual_duration": int(p6.actual_duration) if p6.actual_duration else None,
        "remaining_duration": int(p6.remaining_duration) if p6.remaining_duration else None,
        "spi": round(p6.schedule_performance_index, 2) if p6.schedule_performance_index else None,
        "cpi": round(p6.cost_performance_index, 2) if p6.cost_performance_index else None,
        "planned_cost": round(p6.planned_cost, 2) if p6.planned_cost is not None else None,
        "actual_total_cost": round(p6.actual_total_cost, 2) if p6.actual_total_cost is not None else None,
        "current_budget": round(p6.current_budget, 2) if p6.current_budget is not None else None,
        "baseline_total_cost": round(p6.baseline_total_cost, 2) if p6.baseline_total_cost is not None else None,
        "total_cost_variance": round(p6.total_cost_variance, 2) if p6.total_cost_variance is not None else None,
        "total_float_hours": int(p6.total_float) if p6.total_float is not None else None,
        "finish_date_variance_hours": int(p6.finish_date_variance) if p6.finish_date_variance is not None else None,
        "baseline_variance_days": schedule["baseline_variance_days"],
        "activity_count": len(activities),
        "completed_activities": completed,
        "in_progress_activities": in_progress,
        "not_started_activities": not_started,
        "pending_activities": in_progress + not_started,
        "delayed_activity_count": schedule["delayed_activity_count"],
        "delayed_pending_activity_count": delayed_pending,
        "delayed_completed_activity_count": delayed_completed,
        "max_activity_drift_days": schedule["max_activity_drift_days"],
        "critical_activity_count": schedule["critical_activity_count"],
        "baseline_start": p6.baseline_start_date.isoformat() if p6.baseline_start_date else None,
        "baseline_finish": p6.baseline_finish_date.isoformat() if p6.baseline_finish_date else None,
        "baseline_duration": int(p6.baseline_duration) if p6.baseline_duration else None,
        "last_synced_at": p6.last_synced_at.isoformat() if p6.last_synced_at else None,
        "_source_table": "p6_project",
    }


def p6_get_critical_activities(db: Session, project_id: str, limit: int = 20) -> list[dict]:
    """Get activities on the critical path (total_float <= 0).
    
    Use when: user asks about critical path, critical activities, or delays.
    """
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    if not p6:
        return []
    
    from engine.tools.portfolio_tools import get_project_display_name
    project_name = get_project_display_name(db, project_id)
    
    activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id,
        models.P6Activity.total_float <= 0
    ).order_by(models.P6Activity.total_float.asc()).limit(limit).all()
    
    return [{
        "activity_id": a.activity_id,
        "name": a.name,
        "status": a.status,
        "total_float_hours": int(a.total_float) if a.total_float is not None else None,
        "percent_complete": _activity_percent(a.percent_complete),
        "start_date": a.start_date.isoformat() if a.start_date else None,
        "finish_date": a.finish_date.isoformat() if a.finish_date else None,
        "baseline_finish": a.baseline_finish_date.isoformat() if a.baseline_finish_date else None,
        "drift_days": (a.finish_date - a.baseline_finish_date).days if a.finish_date and a.baseline_finish_date else None,
        "wbs_name": a.wbs_name,
        "project_name": project_name,
        "_source_table": "p6_activity",
    } for a in activities]


def p6_get_portfolio_critical_activities(db: Session, limit: int = 20) -> list[dict]:
    """Get the most critical activities across all P6 projects.

    Use when: user asks about critical path or duration-driving activities
    without naming a specific project.
    """
    mappings = db.query(models.ProjectMapping).all()
    mapping_by_pid = {m.project_id: m for m in mappings if m.project_id}

    rows = db.query(models.P6Activity, models.P6Project).join(
        models.P6Project,
        models.P6Activity.project_object_id == models.P6Project.p6_object_id,
    ).filter(
        models.P6Activity.total_float <= 0
    ).order_by(
        models.P6Activity.total_float.asc()
    ).limit(limit).all()

    result = []
    for activity, project in rows:
        mapping = mapping_by_pid.get(project.project_id)
        project_name = (
            mapping.project_name_from_p6 or mapping.project or project.name or project.project_id
        ) if mapping else (project.name or project.project_id)
        result.append({
            "project_id": project.project_id,
            "project_name": project_name,
            "activity_id": activity.activity_id,
            "name": activity.name,
            "status": activity.status,
            "total_float_hours": int(activity.total_float) if activity.total_float is not None else None,
            "percent_complete": _activity_percent(activity.percent_complete),
            "start_date": activity.start_date.isoformat() if activity.start_date else None,
            "finish_date": activity.finish_date.isoformat() if activity.finish_date else None,
            "baseline_finish": activity.baseline_finish_date.isoformat() if activity.baseline_finish_date else None,
            "drift_days": (
                activity.finish_date - activity.baseline_finish_date
            ).days if activity.finish_date and activity.baseline_finish_date else None,
            "wbs_name": activity.wbs_name,
            "_source_table": "p6_activity",
        })
    return result


def p6_get_delayed_activities(db: Session, project_id: str, min_drift_days: int = 7, limit: int = 20) -> list[dict]:
    """Get activities that are behind schedule (finish date drifted from baseline).
    
    Use when: user asks about delays, schedule slippage, or behind-schedule tasks.
    """
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    if not p6:
        return []
    
    activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id,
        models.P6Activity.finish_date.isnot(None),
        models.P6Activity.baseline_finish_date.isnot(None),
    ).all()
    
    from engine.tools.portfolio_tools import get_project_display_name
    project_name = get_project_display_name(db, project_id)
    
    delayed = []
    for a in activities:
        drift = (a.finish_date - a.baseline_finish_date).days
        if drift >= min_drift_days:
            delayed.append({
                "activity_id": a.activity_id,
                "name": a.name,
                "status": a.status,
                "drift_days": drift,
                "percent_complete": _activity_percent(a.percent_complete),
                "baseline_finish": a.baseline_finish_date.isoformat(),
                "forecast_finish": a.finish_date.isoformat(),
                "is_critical": a.total_float is not None and a.total_float <= 0,
                "wbs_name": a.wbs_name,
                "project_name": project_name,
                "_source_table": "p6_activity",
            })
    
    delayed.sort(key=lambda x: x["drift_days"], reverse=True)
    return delayed[:limit]


def p6_get_pending_activities(db: Session, project_id: str, limit: int = 50) -> dict:
    """Get unfinished P6 activities for a project.

    Pending means the activity status is Not Started or In Progress. This is
    intentionally separate from delayed activities, because delayed-vs-baseline
    can include work that is already completed.
    """
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    if not p6:
        return {"project_id": project_id, "has_data": False, "total_pending": 0, "activities": []}

    from engine.tools.portfolio_tools import get_project_display_name
    project_name = get_project_display_name(db, project_id)

    activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id
    ).all()

    pending = [
        activity for activity in activities
        if (activity.status or "").strip().lower() in {"not started", "in progress"}
    ]
    pending.sort(key=lambda activity: (
        0 if (activity.status or "").strip().lower() == "in progress" else 1,
        -(max(_activity_drift_days(activity) or 0, 0)),
        activity.finish_date or activity.planned_finish_date or datetime.max,
        activity.activity_id or "",
    ))

    breakdown = {}
    delayed_pending = 0
    critical_pending = 0
    for activity in pending:
        status = activity.status or "Unknown"
        breakdown[status] = breakdown.get(status, 0) + 1
        drift = _activity_drift_days(activity)
        if drift is not None and drift >= 7:
            delayed_pending += 1
        if activity.total_float is not None and activity.total_float <= 0:
            critical_pending += 1

    rows = [_activity_payload(activity, project_name) for activity in pending[:limit]]
    return {
        "project_id": project_id,
        "project_name": project_name,
        "has_data": True,
        "definition": "Pending activities are P6 activities with status Not Started or In Progress.",
        "total_pending": len(pending),
        "status_breakdown": breakdown,
        "delayed_pending_count": delayed_pending,
        "critical_pending_count": critical_pending,
        "returned_count": len(rows),
        "has_more": len(pending) > len(rows),
        "activities": rows,
        "_source_table": "p6_activity",
        "_synced_at": p6.last_synced_at.isoformat() if p6.last_synced_at else None,
    }


def p6_get_activity_status_breakdown(db: Session, project_id: str) -> dict:
    """Get activity count breakdown by status for a project.
    
    Use when: user asks "how many activities are completed/in-progress/not started?"
    """
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    if not p6:
        return {"total": 0, "breakdown": {}}
    
    activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id
    ).all()
    
    breakdown = {}
    for a in activities:
        status = a.status or "Unknown"
        breakdown[status] = breakdown.get(status, 0) + 1
    
    from engine.tools.portfolio_tools import get_project_display_name
    return {
        "project_id": project_id,
        "project_name": get_project_display_name(db, project_id),
        "total": len(activities),
        "breakdown": breakdown,
        "_source_table": "p6_activity",
        "_synced_at": p6.last_synced_at.isoformat() if p6.last_synced_at else None,
    }


def p6_get_block_status(db: Session, project_id: str, limit: int = 50) -> dict:
    """Get Block/WTG commissioning status from P6 COD and Trial Run activities.

    A pending block means COD is not completed for that Block/WTG. Trial Run is
    reported separately so commissioned and trial-run-only states do not blur.
    """
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    if not p6:
        return {"project_id": project_id, "has_data": False, "total_blocks": 0, "blocks": []}

    from engine.tools.portfolio_tools import get_project_display_name
    project_name = get_project_display_name(db, project_id)

    all_blocks: set[str] = set()
    for node in db.query(models.P6WBSNode).filter(models.P6WBSNode.project_object_id == p6.p6_object_id).all():
        block = _extract_block_name(node.wbs_name)
        if block:
            all_blocks.add(block)

    milestone_activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id,
        (
            models.P6Activity.name.ilike("%COD%") |
            models.P6Activity.name.ilike("%Trial%") |
            models.P6Activity.name.ilike("%Trail%")
        )
    ).all()

    for activity in milestone_activities:
        block = _extract_block_name(activity.name) or _extract_block_name(activity.wbs_name)
        if block:
            all_blocks.add(block)

    block_status = {
        block: {
            "block": block,
            "cod_status": "Not Started",
            "trial_run_status": "Not Started",
            "overall_status": "Pending",
            "cod_completed": False,
            "trial_run_completed": False,
            "cod_finish": None,
            "trial_run_finish": None,
            "cod_activities": [],
            "trial_run_activities": [],
        }
        for block in all_blocks
    }

    for activity in milestone_activities:
        block = _extract_block_name(activity.name) or _extract_block_name(activity.wbs_name)
        if not block or block not in block_status:
            continue
        name = (activity.name or "").lower()
        is_cod = "cod" in name
        is_trial = "trial" in name or "trail" in name
        if not is_cod and not is_trial:
            continue

        payload = {
            "activity_id": activity.activity_id,
            "name": activity.name,
            "status": activity.status,
            "percent_complete": _activity_percent(activity.percent_complete),
            "actual_finish": activity.actual_finish_date.isoformat() if activity.actual_finish_date else None,
            "finish_date": activity.finish_date.isoformat() if activity.finish_date else None,
        }

        if is_cod:
            block_status[block]["cod_activities"].append(payload)
            if (activity.status or "").strip().lower() == "completed":
                block_status[block]["cod_completed"] = True
                block_status[block]["cod_status"] = "Completed"
                finish = activity.actual_finish_date or activity.finish_date
                block_status[block]["cod_finish"] = finish.isoformat() if finish else None
        elif is_trial:
            block_status[block]["trial_run_activities"].append(payload)
            if (activity.status or "").strip().lower() == "completed":
                block_status[block]["trial_run_completed"] = True
                block_status[block]["trial_run_status"] = "Completed"
                finish = activity.actual_finish_date or activity.finish_date
                block_status[block]["trial_run_finish"] = finish.isoformat() if finish else None

    for status in block_status.values():
        if status["cod_completed"]:
            status["overall_status"] = "COD Completed"
        elif status["trial_run_completed"]:
            status["overall_status"] = "Trial Run Completed; COD Pending"

    blocks = sorted(block_status.values(), key=lambda item: item["block"])
    pending_blocks = [block for block in blocks if not block["cod_completed"]]
    return {
        "project_id": project_id,
        "project_name": project_name,
        "has_data": bool(blocks),
        "definition": "Pending blocks are Blocks/WTGs where COD is not completed in P6.",
        "total_blocks": len(blocks),
        "cod_completed_blocks": len(blocks) - len(pending_blocks),
        "pending_cod_blocks": len(pending_blocks),
        "trial_run_completed_cod_pending_blocks": sum(
            1 for block in pending_blocks if block["trial_run_completed"]
        ),
        "returned_count": min(len(blocks), limit),
        "has_more": len(blocks) > limit,
        "blocks": blocks[:limit],
        "pending_blocks": pending_blocks[:limit],
        "_source_table": "p6_activity,p6_wbs_node",
        "_synced_at": p6.last_synced_at.isoformat() if p6.last_synced_at else None,
    }


def p6_list_all_projects(db: Session) -> dict:
    """List all P6 projects with core metrics.
    
    Use when: user asks about portfolio overview, all projects, or doesn't specify a project.
    """
    projects = db.query(models.P6Project).all()
    
    # Build a mapping lookup for project names
    all_mappings = db.query(models.ProjectMapping).all()
    mapping_by_pid = {m.project_id: m for m in all_mappings}
    
    result = []
    for p in projects:
        m = mapping_by_pid.get(p.project_id)
        display_name = (m.project_name_from_p6 or m.project or p.name) if m else p.name
        if "demo" in display_name.lower():
            continue
        result.append({
            "project_id": p.project_id,
            "project_name": display_name,
            "p6_name": p.name,
            "status": p.status,
            "spi": round(p.schedule_performance_index, 2) if p.schedule_performance_index else None,
            "cpi": round(p.cost_performance_index, 2) if p.cost_performance_index else None,
            "duration_pct_complete": round(p.duration_percent_complete, 1) if p.duration_percent_complete else None,
            "finish_date": p.finish_date.isoformat() if p.finish_date else None,
            "total_float_hours": int(p.total_float) if p.total_float is not None else None,
            "activity_count": p.activity_count,
            "last_synced_at": p.last_synced_at.isoformat() if p.last_synced_at else None,
            "_source_table": "p6_project",
        })
    return {
        "total_projects": len(result),
        "projects": result
    }


def p6_get_wbs_tree(db: Session, project_id: str) -> list[dict]:
    """Get WBS hierarchy for a project (tree structure).
    
    Use when: user asks about WBS, work breakdown, or project structure.
    """
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    if not p6:
        return []
    
    nodes = db.query(models.P6WBSNode).filter(
        models.P6WBSNode.project_object_id == p6.p6_object_id
    ).all()
    
    return [{
        "p6_object_id": n.p6_object_id,
        "wbs_code": n.wbs_code,
        "wbs_name": n.wbs_name,
        "parent_object_id": n.parent_object_id,
        "is_block": n.is_block,
        "_source_table": "p6_wbs_node",
    } for n in nodes]


def p6_get_freshness(db: Session, project_id: str) -> dict:
    """Get the last sync timestamp for a P6 project.
    
    Use when: determining if cached data is still valid (Step 2 of pipeline).
    """
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    
    if not p6:
        return {"project_id": project_id, "synced_at": None, "exists": False}
    
    return {
        "project_id": project_id,
        "synced_at": p6.last_synced_at.isoformat() if p6.last_synced_at else None,
        "data_date": p6.data_date.isoformat() if p6.data_date else None,
        "exists": True,
    }
