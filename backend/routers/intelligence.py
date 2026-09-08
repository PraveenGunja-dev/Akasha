"""
Akasha Intelligence API — REST endpoints for the Intelligence Engine.

All endpoints are READ-ONLY. They query existing data and compute
intelligence on-the-fly with in-memory caching.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
import time
import logging

from database import get_db
from engine.intelligence.core import get_project_intelligence, get_portfolio_intelligence
from engine.intelligence.narrative_engine import generate_executive_briefing
from engine.intelligence.project_story import investigate_single_activity

router = APIRouter(prefix="/api/intelligence", tags=["Intelligence"])
logger = logging.getLogger(__name__)

# In-memory cache (same pattern as existing routers)
_INTEL_CACHE = {}
_CACHE_TTL = 300  # 5 minutes


def _cache_get(key: str):
    if key in _INTEL_CACHE:
        entry = _INTEL_CACHE[key]
        if time.time() - entry["timestamp"] < _CACHE_TTL:
            return entry["data"]
    return None


def _cache_set(key: str, data):
    _INTEL_CACHE[key] = {"data": data, "timestamp": time.time()}


# ──────────────────────────────────────────────
# PROJECT-LEVEL INTELLIGENCE
# ──────────────────────────────────────────────

@router.get("/{project_id}")
def get_intelligence(project_id: str, nocache: bool = False, db: Session = Depends(get_db)):
    """
    Full intelligence report for a single project.
    Returns insights, next steps, risk assessment, predictions across all domains.
    """
    cache_key = f"intel_{project_id}"
    if not nocache:
        cached = _cache_get(cache_key)
        if cached:
            return cached

    result = get_project_intelligence(db, project_id)
    _cache_set(cache_key, result)
    return result


@router.get("/{project_id}/insights")
def get_insights(project_id: str, severity: Optional[str] = None,
                 domain: Optional[str] = None, db: Session = Depends(get_db)):
    """Get key insights for a project, optionally filtered by severity or domain."""
    cache_key = f"intel_{project_id}"
    cached = _cache_get(cache_key)
    if not cached:
        cached = get_project_intelligence(db, project_id)
        _cache_set(cache_key, cached)

    insights = cached.get("top_insights", [])

    if severity:
        insights = [i for i in insights if i.get("severity") == severity.lower()]
    if domain:
        insights = [i for i in insights if i.get("domain") == domain.lower()]

    return {
        "project_id": project_id,
        "project_name": cached.get("project_name"),
        "total_insights": len(insights),
        "insights": insights,
    }


@router.get("/{project_id}/next-steps")
def get_next_steps(project_id: str, db: Session = Depends(get_db)):
    """Get prioritized recommended actions for a project."""
    cache_key = f"intel_{project_id}"
    cached = _cache_get(cache_key)
    if not cached:
        cached = get_project_intelligence(db, project_id)
        _cache_set(cache_key, cached)

    return {
        "project_id": project_id,
        "project_name": cached.get("project_name"),
        "next_steps": cached.get("next_steps", []),
    }


@router.get("/{project_id}/risk")
def get_risk(project_id: str, db: Session = Depends(get_db)):
    """Get unified risk assessment for a project."""
    cache_key = f"intel_{project_id}"
    cached = _cache_get(cache_key)
    if not cached:
        cached = get_project_intelligence(db, project_id)
        _cache_set(cache_key, cached)

    return {
        "project_id": project_id,
        "project_name": cached.get("project_name"),
        "overall_status": cached.get("overall_status"),
        "health_scores": cached.get("health_scores"),
        "primary_bottleneck": cached.get("primary_bottleneck"),
        "risk": cached.get("risk"),
    }


@router.get("/{project_id}/predictions")
def get_predictions(project_id: str, db: Session = Depends(get_db)):
    """Get forward-looking predictions and early warnings for a project."""
    cache_key = f"intel_{project_id}"
    cached = _cache_get(cache_key)
    if not cached:
        cached = get_project_intelligence(db, project_id)
        _cache_set(cache_key, cached)

    return {
        "project_id": project_id,
        "project_name": cached.get("project_name"),
        "predictions": cached.get("predictions"),
    }


@router.get("/{project_id}/schedule")
def get_schedule_intelligence(project_id: str, db: Session = Depends(get_db)):
    """Get schedule intelligence: delay waterfall, block hotspots, critical path."""
    cache_key = f"intel_{project_id}"
    cached = _cache_get(cache_key)
    if not cached:
        cached = get_project_intelligence(db, project_id)
        _cache_set(cache_key, cached)

    return {
        "project_id": project_id,
        "project_name": cached.get("project_name"),
        "schedule": cached.get("schedule"),
    }


@router.get("/{project_id}/materials")
def get_material_intelligence(project_id: str, db: Session = Depends(get_db)):
    """Get material/procurement intelligence: PO tracking, vendor scorecards, gaps."""
    cache_key = f"intel_{project_id}"
    cached = _cache_get(cache_key)
    if not cached:
        cached = get_project_intelligence(db, project_id)
        _cache_set(cache_key, cached)

    return {
        "project_id": project_id,
        "project_name": cached.get("project_name"),
        "materials": cached.get("materials"),
    }


@router.get("/{project_id}/transmission")
def get_transmission_intelligence(project_id: str, db: Session = Depends(get_db)):
    """Get transmission intelligence: connectivity readiness, COD impact."""
    cache_key = f"intel_{project_id}"
    cached = _cache_get(cache_key)
    if not cached:
        cached = get_project_intelligence(db, project_id)
        _cache_set(cache_key, cached)

    return {
        "project_id": project_id,
        "project_name": cached.get("project_name"),
        "transmission": cached.get("transmission"),
    }


@router.get("/{project_id}/narrative")
def get_intelligence_narrative(project_id: str, db: Session = Depends(get_db)):
    """Generate an AI-written executive narrative based on the intelligence data."""
    # Note: We don't want to heavily cache the narrative generation if we want fresh LLM outputs,
    # but we DO cache it for 5 mins to prevent spamming the LLM endpoint on page reloads.
    cache_key = f"intel_narrative_{project_id}"
    cached_narrative = _cache_get(cache_key)
    if cached_narrative:
        return cached_narrative

    # Get the raw intelligence data
    intel_cache_key = f"intel_{project_id}"
    intel_data = _cache_get(intel_cache_key)
    if not intel_data:
        intel_data = get_project_intelligence(db, project_id)
        _cache_set(intel_cache_key, intel_data)
        
    narrative_text = generate_executive_briefing(intel_data)
    
    result = {
        "project_id": project_id,
        "project_name": intel_data.get("project_name"),
        "narrative": narrative_text
    }
    
    _cache_set(cache_key, result)
    return result


@router.get("/{project_id}/story")
def get_project_story_endpoint(project_id: str, nocache: bool = False, db: Session = Depends(get_db)):
    """
    Project-Level Intelligence Story:
    Returns full connected story, executive health radar (8 dimensions),
    top 5 active delays with root causes, contractor impacts, commercial exposure,
    missing interaction gaps (Cases A-E), and pre-filtered answers to the 9 core questions.
    """
    intel = get_intelligence(project_id, nocache=nocache, db=db)
    return intel.get("story", {})


@router.get("/{project_id}/activity/{activity_id}/investigate")
def investigate_activity_endpoint(project_id: str, activity_id: str, db: Session = Depends(get_db)):
    """
    'Why is this delayed?' first-class deep investigation for any P6 activity.
    Returns:
    DELAY → ACTIVITY → PROJECT/PACKAGE → ISSUE/RFI → ROOT CAUSE → RESPONSIBLE PARTY
          → RESOLUTION → SCHEDULE IMPACT → INVOICE/SLR → SAP → COST IMPACT
    Includes multi-tier confidence score and source evidence.
    """
    return investigate_single_activity(db, project_id, activity_id)


@router.get("/{project_id}/timeline")
def get_project_timeline_endpoint(project_id: str, db: Session = Depends(get_db)):
    """
    Unified project timeline combining chronological events across:
    P6 Schedule Shifts, Pulse RFI Inspections, Pulse NC Non-Conformances,
    and E-Invoice commercial submissions/approvals.
    """
    intel = get_intelligence(project_id, db=db)
    story = intel.get("story", {})
    return {
        "project_id": project_id,
        "project_name": intel.get("project_name"),
        "total_events": len(story.get("timeline", [])),
        "timeline": story.get("timeline", [])
    }


@router.get("/{project_id}/gaps")
def get_project_gaps_endpoint(project_id: str, db: Session = Depends(get_db)):
    """
    Missing Interaction & Discrepancy Detection:
    Cases A through E (Unexplained Delays, Dormant RFIs, Inferred Links, Unlinked Commercials, Commercial Drift).
    """
    intel = get_intelligence(project_id, db=db)
    story = intel.get("story", {})
    return {
        "project_id": project_id,
        "project_name": intel.get("project_name"),
        "gaps": story.get("gaps", [])
    }


@router.get("/{project_id}/report")
def generate_project_report_endpoint(project_id: str, db: Session = Depends(get_db)):
    """
    Generates an executive-ready Adani-branded PDF (.pdf) and Word (.docx) report
    complete with 4-quadrant visual analytics charts, critical path delayed activities,
    contractor accountability, and action plan.
    """
    from engine.intelligence.report_generator import build_project_intelligence_docx
    docx_fn, path, size, metrics = build_project_intelligence_docx(db, project_id)
    pdf_fn = metrics.get("pdf_filename", docx_fn.replace(".docx", ".pdf"))
    return {
        "status": "SUCCESS",
        "docx_url": f"/akasha/api/reports/download/{docx_fn}",
        "pdf_url": f"/akasha/api/reports/download/{pdf_fn}",
        "docx_filename": docx_fn,
        "pdf_filename": pdf_fn,
        "metrics": metrics
    }



# ──────────────────────────────────────────────
# PORTFOLIO-LEVEL INTELLIGENCE
# ──────────────────────────────────────────────

@router.get("/portfolio/summary")
def get_portfolio_summary(
    portfolio: Optional[str] = None,
    phase: Optional[str] = None,
    nocache: bool = False,
    db: Session = Depends(get_db)
):
    """
    Portfolio-level intelligence summary.
    Returns top projects needing attention, portfolio health, and aggregate insights.
    """
    cache_key = f"portfolio_{portfolio or 'all'}_{phase or 'all'}"
    if not nocache:
        cached = _cache_get(cache_key)
        if cached:
            return cached

    result = get_portfolio_intelligence(db, portfolio, phase)
    _cache_set(cache_key, result)
    return result


@router.get("/portfolio/hotspots")
def get_portfolio_hotspots(
    portfolio: Optional[str] = None,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get top N projects needing attention (worst health scores)."""
    cache_key = f"portfolio_{portfolio or 'all'}_all"
    cached = _cache_get(cache_key)
    if not cached:
        cached = get_portfolio_intelligence(db, portfolio)
        _cache_set(cache_key, cached)

    return {
        "hotspots": cached.get("hotspots", [])[:limit],
        "total_projects": cached.get("total_projects"),
        "critical_count": cached.get("critical_projects"),
    }
