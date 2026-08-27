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
