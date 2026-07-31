"""
Akasha Tools Layer — P6 Schedule Data Tools

MCP-style tool functions that provide deterministic, read-only access
to Primavera P6 schedule data. These are the "hands" the agents use.

Naming convention: p6_* prefix on all tools (per MCP builder best practices).
"""

from datetime import date, datetime
import logging
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from services.project_catalog_service import ProjectCatalogService
from services.schedule_metrics_service import ScheduleMetricsService

logger = logging.getLogger(__name__)


def p6_get_portfolio_milestone_risks(
    db: Session, portfolio: str | None = None, limit: int = 20
) -> dict:
    """Rank projects with incomplete P6 milestone activities due in their current data month."""
    projects = [
        project for project in ProjectCatalogService.list_projects(db, portfolio)
        if project.project_id
    ]
    rows = []
    cutoffs = []
    for project in projects:
        p6 = db.query(models.P6Project).filter(
            models.P6Project.project_id == project.project_id
        ).first()
        if p6 is None:
            continue
        anchor_value = p6.data_date or datetime.utcnow()
        anchor = anchor_value.date() if isinstance(anchor_value, datetime) else anchor_value
        if not isinstance(anchor, date):
            anchor = datetime.utcnow().date()
        month_start = anchor.replace(day=1)
        next_month = (
            month_start.replace(year=month_start.year + 1, month=1)
            if month_start.month == 12 else month_start.replace(month=month_start.month + 1)
        )
        milestones = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6.p6_object_id,
            func.lower(func.coalesce(models.P6Activity.type, "")).contains("milestone"),
            models.P6Activity.finish_date >= datetime.combine(month_start, datetime.min.time()),
            models.P6Activity.finish_date < datetime.combine(next_month, datetime.min.time()),
        ).all()
        at_risk = []
        for activity in milestones:
            completed = bool(activity.actual_finish_date) or "complete" in str(activity.status or "").casefold()
            if completed:
                continue
            baseline_slip = (
                (activity.finish_date - activity.baseline_finish_date).days
                if activity.finish_date and activity.baseline_finish_date else None
            )
            if activity.finish_date.date() <= anchor or (activity.total_float is not None and activity.total_float <= 0) or (baseline_slip or 0) > 0:
                at_risk.append({
                    "activity_id": activity.activity_id,
                    "name": activity.name,
                    "finish_date": activity.finish_date.isoformat() if activity.finish_date else None,
                    "baseline_finish": activity.baseline_finish_date.isoformat() if activity.baseline_finish_date else None,
                    "baseline_slip_days": baseline_slip,
                    "total_float_hours": activity.total_float,
                })
        if at_risk:
            at_risk.sort(key=lambda item: (
                item["finish_date"] or "9999-12-31",
                item["total_float_hours"] if item["total_float_hours"] is not None else float("inf"),
            ))
            rows.append({
                "project_id": project.project_id,
                "project_name": project.display_name,
                "milestones_due_this_month": len(milestones),
                "milestones_at_risk": len(at_risk),
                "at_risk_milestones": at_risk[:5],
                "data_as_of": anchor.isoformat(),
            })
        cutoffs.append(anchor.isoformat())
    rows.sort(key=lambda item: (-item["milestones_at_risk"], item["project_name"]))
    return {
        "period": "current_month",
        "period_definition": "Calendar month anchored independently to each project's latest P6 data date",
        "projects_evaluated": len(projects),
        "projects_at_risk": len(rows),
        "projects": rows[:limit],
        "latest_data_as_of": max(cutoffs, default=None),
        "warnings": [
            "Risk means an incomplete milestone is due/past due, has non-positive float, or has slipped from its baseline finish; it is not a probabilistic forecast."
        ],
        "_source_tables": ["project_mapping", "p6_project", "p6_activity"],
    }


def p6_get_project_summary(db: Session, project_id: str) -> dict | None:
    """Get high-level project summary: dates, native P6 metrics, activity counts.
    
    Use when: user asks about a specific project's overall status.
    Returns: dict with schedule, cost, and progress metrics, or None if not found.
    """
    metrics = ScheduleMetricsService.get_by_project_id(db, project_id)
    if not metrics.p6_available:
        return None
    project_name = ProjectCatalogService.get_display_name(
        db, project_id, fallback=metrics.name
    )
    
    return {
        "project_id": project_id,
        "project_name": project_name,
        "name": metrics.name,
        "status": metrics.status,
        "start_date": metrics.start_date.isoformat() if metrics.start_date else None,
        "finish_date": metrics.finish_date.isoformat() if metrics.finish_date else None,
        "forecast_finish": metrics.finish_date.isoformat() if metrics.finish_date else None,
        "planned_start": metrics.planned_start.isoformat() if metrics.planned_start else None,
        "scheduled_finish": metrics.scheduled_finish.isoformat() if metrics.scheduled_finish else None,
        "must_finish_by": metrics.must_finish_by.isoformat() if metrics.must_finish_by else None,
        "data_date": metrics.data_date.isoformat() if metrics.data_date else None,
        "duration_percent_complete": metrics.duration_percent_complete,
        "planned_duration": int(metrics.planned_duration) if metrics.planned_duration is not None else None,
        "actual_duration": int(metrics.actual_duration) if metrics.actual_duration is not None else None,
        "remaining_duration": int(metrics.remaining_duration) if metrics.remaining_duration is not None else None,
        "duration_field_semantics": (
            "planned_duration, actual_duration, and remaining_duration are independent native P6 "
            "summary durations in hours; they are not earned hours and must not be used to derive progress_pct"
        ),
        "spi": round(metrics.spi, 4) if metrics.spi is not None else None,
        "cpi": round(metrics.cpi, 4) if metrics.cpi is not None else None,
        "total_float_hours": int(metrics.total_float) if metrics.total_float is not None else None,
        # Legacy compatibility field; the canonical P6 value is stored in days.
        "finish_date_variance_hours": int(metrics.finish_date_variance * 24) if metrics.finish_date_variance is not None else None,
        "finish_date_variance_days": metrics.finish_date_variance,
        "delay_reference_finish": (
            metrics.delay_reference_finish.isoformat()
            if metrics.delay_reference_finish else None
        ),
        "forecast_vs_reference_days": metrics.forecast_vs_reference_days,
        "forecast_vs_reference_units": "days",
        "forecast_vs_reference_semantics": (
            "forecast_finish minus delay_reference_finish; positive values mean forecast late"
        ),
        "activity_count": metrics.activity_count,
        "completed_activities": metrics.completed_activities,
        "in_progress_activities": metrics.in_progress_activities,
        "not_started_activities": metrics.not_started_activities,
        "baseline_start": metrics.baseline_start.isoformat() if metrics.baseline_start else None,
        "baseline_finish": metrics.baseline_finish.isoformat() if metrics.baseline_finish else None,
        "baseline_duration": int(metrics.baseline_duration) if metrics.baseline_duration else None,
        "last_synced_at": metrics.last_synced_at.isoformat() if metrics.last_synced_at else None,
        "p6_available": metrics.p6_available,
        "progress_pct": metrics.progress_pct,
        "progress_formula": metrics.progress_formula,
        "progress_formula_version": metrics.progress_formula_version,
        "progress_units": metrics.progress_units,
        "progress_unit": metrics.progress_units,
        "is_delayed": metrics.is_delayed,
        "schedule_health": "Delayed" if metrics.is_delayed else "On Track",
        "delay_formula": metrics.delay_formula,
        "finish_date_variance": metrics.finish_date_variance,
        "finish_date_variance_units": metrics.finish_date_variance_units,
        "finish_date_variance_unit": metrics.finish_date_variance_units,
        "duration_units": metrics.duration_units,
        "total_float_units": metrics.total_float_units,
        "activity_counts": metrics.activity_counts,
        "freshness": metrics.freshness,
        "_source_table": "p6_project",
    }


def p6_get_critical_activities(db: Session, project_id: str, limit: int = 20) -> list[dict]:
    """Get activities on the critical path (total_float <= 0).
    
    Use when: user asks about critical path, critical activities, or delays.
    """
    metrics = ScheduleMetricsService.get_by_project_id(db, project_id)
    project_name = ProjectCatalogService.get_display_name(
        db, project_id, fallback=metrics.name
    )
    activities = ScheduleMetricsService.get_critical_activities(
        db, project_id, limit=limit
    )
    
    return [{
        "activity_id": activity["activity_id"],
        "name": activity["name"],
        "status": activity["status"],
        "total_float_hours": int(activity["total_float"]) if activity["total_float"] is not None else None,
        "percent_complete": activity["percent_complete"],
        "start_date": activity["start_date"],
        "finish_date": activity["finish_date"],
        "baseline_finish": activity["baseline_finish"],
        "drift_days": activity["drift_days"],
        "wbs_name": activity["wbs_name"],
        "project_name": project_name,
        "_source_table": "p6_activity",
    } for activity in activities]


def p6_get_delayed_activities(db: Session, project_id: str, min_drift_days: int = 7, limit: int = 20) -> list[dict]:
    """Get activities that are behind schedule (finish date drifted from baseline).
    
    Use when: user asks about delays, schedule slippage, or behind-schedule tasks.
    """
    metrics = ScheduleMetricsService.get_by_project_id(db, project_id)
    project_name = ProjectCatalogService.get_display_name(
        db, project_id, fallback=metrics.name
    )
    return [{
        "activity_id": activity["activity_id"],
        "name": activity["name"],
        "status": activity["status"],
        "drift_days": activity["drift_days"],
        "percent_complete": activity["percent_complete"],
        "baseline_finish": activity["baseline_finish"],
        "forecast_finish": activity["finish_date"],
        "is_critical": activity["is_critical"],
        "wbs_name": activity["wbs_name"],
        "project_name": project_name,
        "_source_table": "p6_activity",
    } for activity in ScheduleMetricsService.get_delayed_activities(
        db, project_id, min_drift_days=min_drift_days, limit=limit
    )]


def p6_get_activity_status_breakdown(db: Session, project_id: str) -> dict:
    """Get activity count breakdown by status for a project.
    
    Use when: user asks "how many activities are completed/in-progress/not started?"
    """
    metrics = ScheduleMetricsService.get_by_project_id(db, project_id)
    if not metrics.p6_available:
        return {
            "project_id": project_id,
            "has_data": False,
            "total": None,
            "breakdown": None,
        }
    
    breakdown = ScheduleMetricsService.get_activity_status_breakdown(db, project_id)
    return {
        "project_id": project_id,
        "project_name": ProjectCatalogService.get_display_name(
            db, project_id, fallback=metrics.name
        ),
        "has_data": True,
        "total": sum(breakdown.values()),
        "breakdown": breakdown,
        "_source_table": "p6_activity",
        "_synced_at": metrics.freshness["last_synced_at"],
    }


def p6_get_activities(
    db: Session,
    project_id: str,
    status: str = "all",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """List project activities, optionally filtered by a canonical activity status."""
    status_value = None if status == "all" else {
        "completed": "Completed",
        "in_progress": "In Progress",
        "not_started": "Not Started",
    }[status]
    page = ScheduleMetricsService.get_activity_page(
        db, project_id, status=status_value, limit=limit, offset=offset
    )
    if not page["exists"]:
        return {
            "project_id": project_id,
            "has_data": False,
            "total_matching": None,
            "activities": [],
        }

    metrics = page["metrics"]
    activities = page["activities"]
    return {
        "project_id": project_id,
        "project_name": ProjectCatalogService.get_display_name(
            db, project_id, fallback=metrics.name
        ),
        "has_data": page["total_matching"] > 0,
        "status_filter": status,
        "total_matching": page["total_matching"],
        "returned": len(activities),
        "offset": offset,
        "activities": [{
            "activity_id": activity["activity_id"],
            "name": activity["name"],
            "status": activity["status"],
            "percent_complete": activity["percent_complete"],
            "start_date": activity["start_date"],
            "finish_date": activity["finish_date"],
            "wbs_name": activity["wbs_name"],
            "wbs_code": activity["wbs_code"],
        } for activity in activities],
        "data_date": metrics.freshness["data_date"],
        "last_synced_at": metrics.freshness["last_synced_at"],
        "_source_table": "p6_activity",
    }


def p6_list_all_projects(db: Session, portfolio: str | None = None) -> dict:
    """List all portfolio projects with P6 metrics when available.
    
    The project mapping is the authoritative portfolio population, matching the
    dashboard. P6 fields are optional because some mapped projects have not yet
    been synchronized into the P6 project table.
    """
    mappings = ProjectCatalogService.list_projects(db, portfolio)
    metrics_by_pid = ScheduleMetricsService.list_by_project_ids(
        db, [project.project_id for project in mappings if project.project_id]
    )
    
    result = []
    for project in mappings:
        metrics = metrics_by_pid.get(
            project.project_id, ScheduleMetricsService.calculate(None)
        )
        result.append({
            "mapping_id": project.mapping_id,
            "project_id": project.project_id,
            "project_name": project.project_name or "Unknown Entity",
            "p6_name": project.p6_mapping_name or metrics.name,
            "status": metrics.status if metrics.p6_available else "P6 data unavailable",
            "p6_available": metrics.p6_available,
            "spi": round(metrics.spi, 4) if metrics.spi is not None else None,
            "cpi": round(metrics.cpi, 4) if metrics.cpi is not None else None,
            "duration_pct_complete": metrics.duration_percent_complete,
            "finish_date": metrics.finish_date.isoformat() if metrics.finish_date else None,
            "total_float_hours": int(metrics.total_float) if metrics.total_float is not None else None,
            "activity_count": metrics.activity_count,
            "last_synced_at": metrics.last_synced_at.isoformat() if metrics.last_synced_at else None,
            "progress_pct": metrics.progress_pct,
            "progress_formula": metrics.progress_formula,
            "progress_formula_version": metrics.progress_formula_version,
            "progress_units": metrics.progress_units,
            "is_delayed": metrics.is_delayed,
            "delay_formula": metrics.delay_formula,
            "finish_date_variance": metrics.finish_date_variance,
            "finish_date_variance_units": metrics.finish_date_variance_units,
            "duration_units": metrics.duration_units,
            "total_float_units": metrics.total_float_units,
            "activity_counts": metrics.activity_counts,
            "freshness": metrics.freshness,
            "_source_table": "project_mapping+p6_project",
        })
    result.sort(key=lambda project: (str(project["project_id"]), project["project_name"]))
    return {
        "total_projects": len(result),
        "projects_with_p6_data": sum(1 for project in result if project["p6_available"]),
        "projects": result
    }


def p6_get_block_period_progress(
    db: Session,
    project_id: str,
    period: str = "last_month",
    days: int = 30,
) -> dict:
    """Rank project blocks by activity completions in the requested month."""
    result = ScheduleMetricsService.get_block_period_progress(
        db, project_id, period=period, days=days
    )
    if result.get("p6_available"):
        result["project_name"] = ProjectCatalogService.get_display_name(
            db, project_id, fallback=result.get("project_name")
        )
        result["_source_tables"] = ["p6_project", "p6_activity", "p6_wbs_node"]
    return result


def p6_get_daily_completion_trend(
    db: Session,
    project_id: str,
    days: int = 30,
) -> dict:
    """Return an honest daily trend based on P6 activity actual-finish events."""
    result = ScheduleMetricsService.get_daily_activity_completion_trend(
        db, project_id, days=days
    )
    if result.get("p6_available"):
        result["project_name"] = ProjectCatalogService.get_display_name(
            db, project_id, fallback=result.get("project_name")
        )
        result["_source_tables"] = ["p6_project", "p6_activity"]
    return result


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
    metrics = ScheduleMetricsService.get_by_project_id(db, project_id)
    if not metrics.p6_available:
        return {"project_id": project_id, "synced_at": None, "exists": False}
    
    return {
        "project_id": project_id,
        "synced_at": metrics.freshness["last_synced_at"],
        "data_date": metrics.freshness["data_date"],
        "exists": True,
    }
