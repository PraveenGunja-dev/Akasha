"""
Akasha Intelligence Engine — Core Orchestrator

Runs all domain analyzers against a project and assembles the unified
intelligence report. This is the single entry point for all intelligence queries.

Read-only: never modifies existing data.
"""

import logging
from datetime import datetime
from sqlalchemy.orm import Session

import models
from engine.intelligence.schedule_intel import analyze_schedule
from engine.intelligence.material_intel import analyze_materials
from engine.intelligence.transmission_intel import analyze_transmission
from engine.intelligence.financial_intel import analyze_financials
from engine.intelligence.quality_intel import analyze_quality
from engine.intelligence.risk_intel import analyze_risk
from engine.intelligence.action_engine import generate_actions
from engine.intelligence.prediction_engine import generate_predictions

logger = logging.getLogger(__name__)


def _resolve_project(db: Session, project_id: str) -> dict:
    """Resolve project_id to all related entities needed for intelligence analysis."""
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()

    if not mapping:
        return None

    p6_proj = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()

    activities = []
    if p6_proj:
        activities = db.query(models.P6Activity).filter(
            models.P6Activity.project_object_id == p6_proj.p6_object_id
        ).all()

    # Resolve WBS for SAP queries
    wbs = mapping.module_wbs
    if wbs and str(wbs).strip().lower() not in ('nan', 'none', 'null', ''):
        wbs = str(wbs).strip()
    else:
        wbs = None

    plant_code = mapping.spv_plant_code
    if plant_code and str(plant_code).strip().lower() not in ('nan', 'none', 'null', ''):
        plant_code = str(plant_code).strip()
    else:
        plant_code = None

    return {
        "mapping": mapping,
        "p6_project": p6_proj,
        "activities": activities,
        "project_id": project_id,
        "project_name": mapping.project_name_from_p6 or mapping.project or project_id,
        "wbs": wbs,
        "plant_code": plant_code,
        "capacity_mw": mapping.capacity_mwac,
        "cluster": mapping.cluster,
        "category": mapping.category,
    }


def get_project_intelligence(db: Session, project_id: str) -> dict:
    """
    Generate a complete intelligence report for a single project.
    This is the main entry point for all intelligence queries.

    Returns a structured dict with insights, next steps, risks, and predictions
    across all domains (schedule, material, transmission, financial, quality).
    """
    ctx = _resolve_project(db, project_id)
    if not ctx:
        return {
            "project_id": project_id,
            "error": "Project not found in mapping table",
            "has_data": False,
        }

    logger.info(f"🧠 Computing intelligence for project: {ctx['project_name']} ({project_id})")

    # Run each domain analyzer independently
    schedule = analyze_schedule(db, ctx)
    materials = analyze_materials(db, ctx)
    transmission = analyze_transmission(db, ctx)
    financials = analyze_financials(db, ctx)
    quality = analyze_quality(db, ctx)

    # Cross-domain risk analysis (reads from all domain results)
    risk = analyze_risk(schedule, materials, transmission, financials, quality, ctx)

    # Generate concrete action items from all insights
    all_insights = (
        schedule.get("insights", []) +
        materials.get("insights", []) +
        transmission.get("insights", []) +
        financials.get("insights", []) +
        quality.get("insights", []) +
        risk.get("insights", [])
    )
    actions = generate_actions(all_insights, ctx)

    # Forward-looking predictions
    predictions = generate_predictions(db, ctx, schedule, materials, transmission)

    # Assemble the unified report
    report = {
        "project_id": project_id,
        "project_name": ctx["project_name"],
        "capacity_mw": ctx["capacity_mw"],
        "cluster": ctx["cluster"],
        "category": ctx["category"],
        "computed_at": datetime.utcnow().isoformat(),
        "has_data": True,

        # Health scores (0-100, higher = better)
        "health_scores": {
            "schedule": schedule.get("health_score", None),
            "material": materials.get("health_score", None),
            "transmission": transmission.get("health_score", None),
            "financial": financials.get("health_score", None),
            "quality": quality.get("health_score", None),
            "overall": risk.get("overall_health", None),
        },

        # Overall status
        "overall_status": risk.get("overall_status", "UNKNOWN"),
        "primary_bottleneck": risk.get("primary_bottleneck", None),
        "total_delay_days": schedule.get("total_delay_days", 0),

        # Domain details
        "schedule": schedule,
        "materials": materials,
        "transmission": transmission,
        "financials": financials,
        "quality": quality,
        "risk": risk,

        # Actionable outputs
        "top_insights": _rank_insights(all_insights)[:10],
        "next_steps": actions,
        "predictions": predictions,
    }

    return report


def get_portfolio_intelligence(db: Session, portfolio: str = None, phase: str = None) -> dict:
    """
    Generate portfolio-level intelligence summary.
    Returns the top projects needing attention with key metrics.
    """
    query = db.query(models.ProjectMapping)
    if portfolio and portfolio.lower() != "all portfolios":
        query = query.filter(
            (models.ProjectMapping.cluster.ilike(f"%{portfolio}%")) |
            (models.ProjectMapping.category.ilike(f"%{portfolio}%"))
        )
    if phase and phase != "ALL":
        is_comm = True if phase == "Commissioned" else False
        query = query.filter(models.ProjectMapping.is_commissioned == is_comm)

    mappings = query.all()

    # Filter out demo projects
    mappings = [m for m in mappings if m.project_name_from_p6 and 'demo' not in m.project_name_from_p6.lower()]

    # Quick health scan for each project (lightweight version)
    project_summaries = []
    for m in mappings:
        if not m.project_id:
            continue
        summary = _quick_project_scan(db, m)
        if summary:
            project_summaries.append(summary)

    # Sort by health (worst first)
    project_summaries.sort(key=lambda x: x.get("overall_health", 100))

    # Portfolio-wide aggregations
    total_projects = len(project_summaries)
    delayed_projects = [p for p in project_summaries if p.get("total_delay_days", 0) > 0]
    critical_projects = [p for p in project_summaries if p.get("overall_status") == "CRITICAL"]
    at_risk_projects = [p for p in project_summaries if p.get("overall_status") == "AT_RISK"]

    # Top insights across portfolio
    portfolio_insights = []
    if critical_projects:
        portfolio_insights.append({
            "severity": "critical",
            "domain": "portfolio",
            "title": f"{len(critical_projects)} projects in CRITICAL status",
            "description": f"Projects: {', '.join(p['project_name'] for p in critical_projects[:5])}",
            "impact": "Immediate executive attention required",
        })
    if len(delayed_projects) > total_projects * 0.5:
        portfolio_insights.append({
            "severity": "high",
            "domain": "portfolio",
            "title": f"{len(delayed_projects)} of {total_projects} projects are delayed ({round(len(delayed_projects)/max(total_projects,1)*100)}%)",
            "description": "More than half the portfolio is behind schedule",
            "impact": "Systemic issue — review planning methodology",
        })

    return {
        "computed_at": datetime.utcnow().isoformat(),
        "total_projects": total_projects,
        "delayed_projects": len(delayed_projects),
        "critical_projects": len(critical_projects),
        "at_risk_projects": len(at_risk_projects),
        "on_track_projects": total_projects - len(delayed_projects),
        "portfolio_health": round(
            sum(p.get("overall_health", 50) for p in project_summaries) / max(total_projects, 1), 1
        ),
        "insights": portfolio_insights,
        "hotspots": project_summaries[:10],  # Top 10 worst projects
        "all_projects": project_summaries,
    }


def _quick_project_scan(db: Session, mapping) -> dict | None:
    """Lightweight project health scan for portfolio view (no deep analysis)."""
    project_id = mapping.project_id
    if not project_id:
        return None

    p6_proj = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()

    if not p6_proj:
        return None

    # Quick schedule health
    total_delay_days = 0
    schedule_health = 50  # default unknown

    if p6_proj.baseline_finish_date and p6_proj.finish_date:
        total_delay_days = max(0, (p6_proj.finish_date - p6_proj.baseline_finish_date).days)

    progress = p6_proj.duration_percent_complete or 0
    if progress > 1:
        progress = progress  # already percentage
    else:
        progress = progress * 100

    # Simple health heuristic
    if total_delay_days == 0:
        schedule_health = 90
    elif total_delay_days <= 15:
        schedule_health = 70
    elif total_delay_days <= 45:
        schedule_health = 50
    elif total_delay_days <= 90:
        schedule_health = 30
    else:
        schedule_health = 10

    # Determine status
    if total_delay_days > 60 or schedule_health < 30:
        status = "CRITICAL"
    elif total_delay_days > 15 or schedule_health < 60:
        status = "AT_RISK"
    else:
        status = "ON_TRACK"

    return {
        "project_id": project_id,
        "project_name": mapping.project_name_from_p6 or mapping.project,
        "cluster": mapping.cluster,
        "category": mapping.category,
        "capacity_mw": mapping.capacity_mwac,
        "progress_pct": round(progress, 1),
        "total_delay_days": total_delay_days,
        "schedule_health": schedule_health,
        "overall_health": schedule_health,  # simplified for portfolio scan
        "overall_status": status,
        "baseline_finish": p6_proj.baseline_finish_date.isoformat() if p6_proj.baseline_finish_date else None,
        "forecast_finish": p6_proj.finish_date.isoformat() if p6_proj.finish_date else None,
    }


def _rank_insights(insights: list) -> list:
    """Rank insights by severity for the top insights panel."""
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return sorted(
        insights,
        key=lambda x: severity_order.get(x.get("severity", "info"), 5)
    )
