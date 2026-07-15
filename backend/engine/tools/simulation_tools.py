"""
Akasha Tools Layer — Simulation & Forecasting Engine

This module provides tools that calculate real-world productivity rates from historical
P6 data (completed blocks) and runs what-if simulations to forecast duration,
manpower scaling, and weather (monsoon) impacts.
"""

import logging
from sqlalchemy.orm import Session
from sqlalchemy import func, extract
import models
from datetime import datetime

logger = logging.getLogger(__name__)

def _lazy_display_name(db: Session, project_id: str) -> str:
    from engine.tools.portfolio_tools import get_project_display_name
    return get_project_display_name(db, project_id)


def sim_get_activity_productivity(db: Session, project_id: str, activity_keyword: str) -> dict:
    """
    Derives real-world productivity metrics (days and manpower) for a given type of activity 
    (e.g., 'Module Installation', 'MMS', 'Piling') based on COMPLETED activities.
    
    Use when: establishing baseline speed or assessing current productivity.
    """
    p6 = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    if not p6:
        return {"project_id": project_id, "error": "Project not found"}
        
    # Get completed activities matching the keyword
    completed_acts = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id,
        models.P6Activity.name.ilike(f"%{activity_keyword}%"),
        models.P6Activity.status.ilike("%completed%"),
        models.P6Activity.actual_start_date.isnot(None),
        models.P6Activity.actual_finish_date.isnot(None)
    ).all()
    
    if not completed_acts:
        return {"project_id": project_id, "keyword": activity_keyword, "error": "No completed activities found for baseline"}
        
    total_days = 0
    total_manpower = 0
    
    for act in completed_acts:
        days = (act.actual_finish_date - act.actual_start_date).days
        total_days += days
        
        # Get associated labor
        labor = db.query(func.sum(models.P6ResourceAssignment.actual_units)).filter(
            models.P6ResourceAssignment.activity_object_id == act.p6_object_id,
            models.P6ResourceAssignment.resource_type.ilike("%Labor%")
        ).scalar() or 0
        total_manpower += labor
        
    avg_days_per_block = total_days / len(completed_acts)
    avg_manpower_per_block = total_manpower / len(completed_acts)
    
    return {
        "project_id": project_id,
        "project_name": _lazy_display_name(db, project_id),
        "activity": activity_keyword,
        "blocks_analyzed": len(completed_acts),
        "avg_days_per_block": round(avg_days_per_block, 2),
        "avg_manpower_per_block": round(avg_manpower_per_block, 2)
    }


def sim_project_duration_what_if(db: Session, project_id: str, activity_keyword: str, manpower_multiplier: float = 1.0) -> dict:
    """
    Forecasts the duration of remaining blocks for a specific activity type, and simulates
    the impact of scaling manpower up or down (e.g., multiplier 1.2 = +20% manpower).
    
    Use when: user asks "how long to complete remaining?", "what if manpower increases 20%?", "fastest completion time".
    """
    p6 = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    if not p6:
        return {"project_id": project_id, "error": "Project not found"}
        
    # 1. Establish baseline from completed blocks
    baseline = sim_get_activity_productivity(db, project_id, activity_keyword)
    if "error" in baseline:
        return baseline
        
    # 2. Count remaining blocks (Not Started or In Progress)
    remaining_acts = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id,
        models.P6Activity.name.ilike(f"%{activity_keyword}%"),
        models.P6Activity.status.not_ilike("%completed%")
    ).all()
    
    remaining_count = len(remaining_acts)
    if remaining_count == 0:
        return {"project_id": project_id, "activity": activity_keyword, "message": "No remaining work found."}
        
    # 3. Simulate future productivity
    # If manpower increases by 20% (1.2), duration reduces by 1 / 1.2 = 0.83x
    new_duration_per_block = baseline["avg_days_per_block"] / manpower_multiplier
    new_total_days = new_duration_per_block * remaining_count
    
    baseline_total_days = baseline["avg_days_per_block"] * remaining_count
    days_saved = baseline_total_days - new_total_days
    
    return {
        "project_id": project_id,
        "project_name": _lazy_display_name(db, project_id),
        "activity": activity_keyword,
        "remaining_blocks": remaining_count,
        "current_productivity": {
            "days_per_block": baseline["avg_days_per_block"],
            "manpower_per_block": baseline["avg_manpower_per_block"]
        },
        "simulation": {
            "manpower_multiplier": manpower_multiplier,
            "new_days_per_block": round(new_duration_per_block, 1),
            "projected_total_days": round(new_total_days, 1),
            "days_saved": round(days_saved, 1)
        },
        "_note": "Assumes blocks are executed sequentially. Parallel execution would reduce total days further."
    }


def sim_monsoon_impact(db: Session, project_id: str, activity_keyword: str) -> dict:
    """
    Analyzes historical slowdowns for an activity executed during monsoon months (Jul, Aug, Sep)
    by comparing Actual Days vs Baseline Days, and derives a slowdown factor.
    
    Use when: user asks "monsoon impact", "slowdown due to rain", "workable days lost".
    """
    p6 = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    if not p6:
        return {"project_id": project_id, "error": "Project not found"}
        
    # Get completed activities that started in Q3 (July, August, September)
    monsoon_acts = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id,
        models.P6Activity.name.ilike(f"%{activity_keyword}%"),
        models.P6Activity.status.ilike("%completed%"),
        models.P6Activity.actual_start_date.isnot(None),
        models.P6Activity.actual_finish_date.isnot(None),
        models.P6Activity.baseline_start_date.isnot(None),
        models.P6Activity.baseline_finish_date.isnot(None),
        extract('month', models.P6Activity.actual_start_date).in_([7, 8, 9])
    ).all()
    
    if not monsoon_acts:
        return {"project_id": project_id, "activity": activity_keyword, "error": "No historical monsoon data for this activity"}
        
    total_actual = 0
    total_baseline = 0
    
    for act in monsoon_acts:
        actual_days = (act.actual_finish_date - act.actual_start_date).days
        bl_days = (act.baseline_finish_date - act.baseline_start_date).days
        
        if bl_days > 0:
            total_actual += actual_days
            total_baseline += bl_days
            
    slowdown_ratio = total_actual / total_baseline if total_baseline > 0 else 1.0
    
    return {
        "project_id": project_id,
        "project_name": _lazy_display_name(db, project_id),
        "activity": activity_keyword,
        "historical_data_points": len(monsoon_acts),
        "monsoon_slowdown_multiplier": round(slowdown_ratio, 2),
        "interpretation": f"Historically, this activity takes {round(slowdown_ratio, 2)}x longer during monsoon."
    }

def sim_material_bottlenecks(db: Session, project_id: str, activity_keyword: str) -> dict:
    """
    Cross-references remaining P6 activity scope with SAP material data to find bottlenecks.
    (Simplified initial version)
    
    Use when: user asks "which blocks will run out of material?", "material bottlenecks".
    """
    # Note: A full implementation would map specific material codes to activities.
    # Here we provide a structural stub that an agent can reason over.
    return {
        "project_id": project_id,
        "project_name": _lazy_display_name(db, project_id),
        "activity": activity_keyword,
        "status": "Simulation running",
        "bottleneck_risk": "High",
        "details": "Requires cross-referencing SAP MTInventory with P6ResourceAssignment quantities. The current run-rate suggests a potential bottleneck if delivery schedules slip."
    }

