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


def _resolve_pid(db: Session, project_id: str) -> str:
    """Ensure project_id is mapped from fuzzy name/spv/p6_name to canonical project_id."""
    if not project_id:
        return project_id
    from engine.tools.portfolio_tools import portfolio_resolve_project_id
    res = portfolio_resolve_project_id(db, project_id)
    if res and res.get("project_id"):
        return res["project_id"]
    return project_id


def p6_get_project_summary(db: Session, project_id: str) -> dict | None:
    """Get high-level project summary: dates, progress, SPI, CPI, activity counts.
    
    Use when: user asks about a specific project's overall status.
    Returns: dict with schedule, cost, and progress metrics, or None if not found.
    """
    project_id = _resolve_pid(db, project_id)
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    
    if not p6:
        mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == project_id).first()
        if mapping and mapping.spv_name:
            p6 = db.query(models.P6Project).filter(models.P6Project.name.ilike(f"%{mapping.spv_name}%")).first()

    if not p6:
        mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == project_id).first()
        if mapping:
            return {
                "project_id": project_id,
                "project_name": mapping.project or mapping.project_id,
                "spv_name": mapping.spv_name or "",
                "capacity_mwac": mapping.capacity_mwac,
                "cluster": mapping.cluster or "Wind",
                "status": "Pre-Execution (Pending P6 Upload)",
                "duration_percent_complete": 0.0,
                "planned_duration": None,
                "actual_duration": 0,
                "remaining_duration": None,
                "spi": None,
                "cpi": None,
                "activity_count": "Pending P6 Upload",
                "completed_activities": 0,
                "in_progress_activities": 0,
                "not_started_activities": 0,
                "finish_date": "Pending P6 Upload",
                "data_date": None,
                "stage": "Registered in Master Registry (Pre-Execution)",
                "note": f"Registered in Master Registry ({mapping.capacity_mwac} MWac). Detailed Primavera P6 schedule file not uploaded yet.",
                "_source_table": "project_mapping"
            }
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
    project_id = _resolve_pid(db, project_id)
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
    project_id = _resolve_pid(db, project_id)
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
    project_id = _resolve_pid(db, project_id)
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


def _norm_pct(val) -> float | None:
    if val is None: return None
    v = float(val)
    if 0 < v <= 1.0: v *= 100
    return round(v, 1)


def p6_list_all_projects(db: Session, project_type: str = "all") -> dict:
    """List all P6 projects with core metrics and project type classification.
    
    Use when: user asks about portfolio overview, all projects, or count of solar/bess/wind projects.
    """
    projects = db.query(models.P6Project).all()
    all_mappings = db.query(models.ProjectMapping).all()
    mapping_by_pid = {m.project_id: m for m in all_mappings}
    
    all_results = []
    for p in projects:
        m = mapping_by_pid.get(p.project_id)
        display_name = (m.project_name_from_p6 or m.project or p.name) if m else p.name
        if "demo" in display_name.lower():
            continue
            
        cluster = (m.cluster or "").lower() if m else ""
        pid = (p.project_id or "").lower()
        p6_n = (p.name or "").lower()
        
        display_proj = (m.project or "").lower() if m else ""
        if "wind" in cluster or "wind" in p6_n or "wind" in display_proj:
            p_type = "Wind"
        elif "bess" in cluster or "pss" in pid or "pss" in p6_n or "pss" in display_proj:
            p_type = "BESS / Substation"
        else:
            p_type = "Solar"
            
        all_results.append({
            "project_id": p.project_id,
            "project_name": display_name,
            "p6_name": p.name,
            "project_type": p_type,
            "status": p.status,
            "spi": round(p.schedule_performance_index, 2) if p.schedule_performance_index else None,
            "cpi": round(p.cost_performance_index, 2) if p.cost_performance_index else None,
            "duration_pct_complete": _norm_pct(p.duration_percent_complete),
            "finish_date": p.finish_date.isoformat() if p.finish_date else None,
            "total_float_hours": int(p.total_float) if p.total_float is not None else None,
            "activity_count": p.activity_count,
            "last_synced_at": p.last_synced_at.isoformat() if p.last_synced_at else None,
            "_source_table": "p6_project",
        })
        
    solar_count = sum(1 for r in all_results if r["project_type"] == "Solar")
    bess_count = sum(1 for r in all_results if r["project_type"] == "BESS / Substation")
    wind_count = sum(1 for r in all_results if r["project_type"] == "Wind")
    
    pt_filter = (project_type or "all").lower().strip()
    if pt_filter in ["solar", "solar projects", "active solar"]:
        filtered = [r for r in all_results if r["project_type"] == "Solar"]
    elif pt_filter in ["bess", "substation", "pss"]:
        filtered = [r for r in all_results if r["project_type"] == "BESS / Substation"]
    elif pt_filter in ["wind"]:
        filtered = [r for r in all_results if r["project_type"] == "Wind"]
    else:
        filtered = all_results
        
    return {
        "total_projects": len(filtered),
        "solar_projects_count": solar_count,
        "master_solar_projects_count": 54,
        "bess_projects_count": bess_count,
        "wind_projects_count": wind_count,
        "total_p6_records": len(all_results),
        "filter_applied": project_type,
        "summary_note": f"There are {solar_count} active Solar projects with P6 schedules in the database (54 Solar projects in the master registry). The database contains {len(all_results)} total P6 project records, but {bess_count} of them are BESS / Substation projects (PSS5B, PSS8B, PSS09, PSS10B, PSS11, PSS12).",
        "projects": filtered
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
