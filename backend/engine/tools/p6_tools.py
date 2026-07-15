"""
Akasha Tools Layer — P6 Schedule Data Tools

MCP-style tool functions that provide deterministic, read-only access
to Primavera P6 schedule data. These are the "hands" the agents use.

Naming convention: p6_* prefix on all tools (per MCP builder best practices).
"""

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)


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
    
    return {
        "project_id": project_id,
        "project_name": project_name,
        "name": p6.name,
        "status": p6.status,
        "start_date": p6.start_date.isoformat() if p6.start_date else None,
        "finish_date": p6.finish_date.isoformat() if p6.finish_date else None,
        "planned_start": p6.planned_start_date.isoformat() if p6.planned_start_date else None,
        "scheduled_finish": p6.scheduled_finish_date.isoformat() if p6.scheduled_finish_date else None,
        "must_finish_by": p6.must_finish_by_date.isoformat() if p6.must_finish_by_date else None,
        "data_date": p6.data_date.isoformat() if p6.data_date else None,
        "duration_percent_complete": round(p6.duration_percent_complete, 1) if p6.duration_percent_complete else None,
        "planned_duration": int(p6.planned_duration) if p6.planned_duration else None,
        "actual_duration": int(p6.actual_duration) if p6.actual_duration else None,
        "remaining_duration": int(p6.remaining_duration) if p6.remaining_duration else None,
        "spi": round(p6.schedule_performance_index, 2) if p6.schedule_performance_index else None,
        "cpi": round(p6.cost_performance_index, 2) if p6.cost_performance_index else None,
        "total_float_hours": int(p6.total_float) if p6.total_float is not None else None,
        "finish_date_variance_hours": int(p6.finish_date_variance) if p6.finish_date_variance is not None else None,
        "activity_count": len(activities),
        "completed_activities": completed,
        "in_progress_activities": in_progress,
        "not_started_activities": not_started,
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
        "percent_complete": round(a.percent_complete, 1) if a.percent_complete else None,
        "start_date": a.start_date.isoformat() if a.start_date else None,
        "finish_date": a.finish_date.isoformat() if a.finish_date else None,
        "baseline_finish": a.baseline_finish_date.isoformat() if a.baseline_finish_date else None,
        "drift_days": (a.finish_date - a.baseline_finish_date).days if a.finish_date and a.baseline_finish_date else None,
        "wbs_name": a.wbs_name,
        "project_name": project_name,
        "_source_table": "p6_activity",
    } for a in activities]


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
                "percent_complete": round(a.percent_complete, 1) if a.percent_complete else None,
                "baseline_finish": a.baseline_finish_date.isoformat(),
                "forecast_finish": a.finish_date.isoformat(),
                "is_critical": a.total_float is not None and a.total_float <= 0,
                "wbs_name": a.wbs_name,
                "project_name": project_name,
                "_source_table": "p6_activity",
            })
    
    delayed.sort(key=lambda x: x["drift_days"], reverse=True)
    return delayed[:limit]


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
