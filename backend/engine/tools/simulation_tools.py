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
from datetime import datetime, timedelta
from statistics import median

logger = logging.getLogger(__name__)


def _norm_pct(value) -> float:
    """duration_percent_complete is stored as a 0-1 fraction here (0.46 = 46%); normalize to 0-100."""
    if value is None:
        return 0.0
    v = float(value)
    return round(v * 100 if v <= 1.5 else v, 1)

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
    n = len(monsoon_acts)

    # A ratio from 1-2 data points isn't "historical" — it's a single anecdote. Report the
    # sample size honestly instead of stating the multiplier with false authority.
    if n < 3:
        confidence = "LOW"
        interpretation = (
            f"Only {n} historical instance{'s' if n != 1 else ''} of this activity during monsoon "
            f"— observed {round(slowdown_ratio, 2)}x slower, but this is not a reliable sample size. "
            f"Treat as anecdotal, not a dependable forecast."
        )
    elif n < 8:
        confidence = "MEDIUM"
        interpretation = (
            f"Based on {n} historical instances, this activity runs about {round(slowdown_ratio, 2)}x "
            f"slower during monsoon — a moderate sample, reasonable but not highly reliable."
        )
    else:
        confidence = "HIGH"
        interpretation = (
            f"Based on {n} historical instances, this activity reliably runs about "
            f"{round(slowdown_ratio, 2)}x slower during monsoon."
        )

    return {
        "project_id": project_id,
        "project_name": _lazy_display_name(db, project_id),
        "activity": activity_keyword,
        "historical_data_points": n,
        "confidence": confidence,
        "monsoon_slowdown_multiplier": round(slowdown_ratio, 2),
        "interpretation": interpretation,
    }

def sim_material_bottlenecks(db: Session, project_id: str, activity_keyword: str) -> dict:
    """
    Cross-references remaining P6 activity scope with SAP material supply data (pending PO
    quantities) to flag potential material bottlenecks.

    Use when: user asks "which blocks will run out of material?", "material bottlenecks".

    LIMITATION: there is no data linking a specific SAP material_code to a specific P6 activity
    type, so this reports project-wide material supply gaps alongside the remaining activity
    count — it does not confirm that a flagged material is actually consumed by activity_keyword.
    """
    p6 = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    if not p6:
        return {"project_id": project_id, "error": "Project not found"}

    remaining_count = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id,
        models.P6Activity.name.ilike(f"%{activity_keyword}%"),
        models.P6Activity.status.not_ilike("%completed%")
    ).count()

    if remaining_count == 0:
        return {
            "project_id": project_id,
            "project_name": _lazy_display_name(db, project_id),
            "activity": activity_keyword,
            "remaining_blocks": 0,
            "message": "No remaining work found for this activity — no bottleneck to assess.",
        }

    from engine.tools.sap_tools import sap_get_material_gaps, sap_get_po_summary
    gaps = sap_get_material_gaps(db, project_id, limit=50)
    has_po_data = sap_get_po_summary(db, project_id).get("has_data", False)

    # 20%/50% thresholds are judgment calls, not measured facts — the real gap_pct per
    # material is always included so the caller can judge severity independently.
    at_risk_materials = [g for g in gaps if g.get("gap_pct", 0) >= 20]

    if not has_po_data:
        risk_level = "Unknown"
        summary = "No SAP PO data found for this project — cannot assess material risk."
    elif not gaps:
        risk_level = "Low"
        summary = "PO data exists and shows no pending gap materials — all tracked materials fully delivered."
    elif at_risk_materials:
        risk_level = "High" if any(g["gap_pct"] >= 50 for g in at_risk_materials) else "Medium"
        summary = f"{len(at_risk_materials)} of {len(gaps)} tracked materials have 20%+ of ordered quantity still undelivered."
    else:
        risk_level = "Low"
        summary = f"None of the {len(gaps)} tracked materials show a significant (20%+) undelivered gap."

    return {
        "project_id": project_id,
        "project_name": _lazy_display_name(db, project_id),
        "activity": activity_keyword,
        "remaining_blocks": remaining_count,
        "risk_level": risk_level,
        "summary": summary,
        "at_risk_materials": at_risk_materials,
        "_caveat": "Materials shown are project-wide SAP supply gaps, not confirmed to be specifically consumed by this activity type — no activity-to-material-code mapping exists in the current schema.",
        "_source_table": "p6_activity, mt_poamount",
    }


def sim_forecast_completion(db: Session, project_id: str) -> dict:
    """
    Forecast a project's completion using ONLY real P6 data — two independent, grounded methods:
      1. P6 schedule forecast: P6's own forecast finish date vs the baseline plan (the slip).
      2. Pace-based forecast: projects the finish from actual progress rate since project start
         (% complete over elapsed time), assuming the average pace continues.
    Reconciles the two, lists milestones at risk of slipping, and reports a confidence level.
    Never invents a date — if the project hasn't started (0% complete) it says so and falls back
    to the baseline plan. This is a projection from existing data, not a guess about the future.

    Use when: user asks "when will X finish?", "expected completion month", "is it on track for
    commissioning?", "which milestones will slip?", "forecast vs baseline".
    """
    p6 = db.query(models.P6Project).filter(models.P6Project.project_id == project_id).first()
    if not p6:
        return {"project_id": project_id, "error": "Project not found"}

    name = _lazy_display_name(db, project_id)
    pct = _norm_pct(p6.duration_percent_complete)

    activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id
    ).all()
    total_acts = len(activities)
    completed_acts = sum(1 for a in activities if a.status and 'complet' in a.status.lower())

    baseline_finish = p6.baseline_finish_date
    p6_forecast = p6.finish_date or p6.scheduled_finish_date
    data_date = p6.data_date or p6.last_synced_at
    start = p6.start_date or p6.planned_start_date

    result = {
        "project_id": project_id,
        "project_name": name,
        "status": p6.status,
        "current_pct_complete": pct,
        "activities": {"total": total_acts, "completed": completed_acts},
        "data_as_of": data_date.date().isoformat() if data_date else None,
        "_source_table": "p6_project, p6_activity",
    }

    # --- Method 1: P6's own schedule forecast vs baseline plan ---
    if p6_forecast and baseline_finish:
        var_days = (p6_forecast - baseline_finish).days
        result["p6_schedule_forecast"] = {
            "forecast_finish": p6_forecast.date().isoformat(),
            "baseline_finish": baseline_finish.date().isoformat(),
            "variance_days": var_days,
            "expected_completion_month": p6_forecast.strftime("%B %Y"),
            "status": "DELAYED" if var_days > 7 else ("AHEAD" if var_days < -7 else "ON TRACK"),
            "_basis": "P6's scheduled finish date vs the project baseline.",
        }

    # --- Method 2: pace-based forecast from actual progress ---
    if start and data_date and 0 < pct < 100:
        elapsed_days = (data_date - start).days
        if elapsed_days > 0:
            projected_total_days = elapsed_days / (pct / 100.0)
            remaining_days = max(projected_total_days - elapsed_days, 0)
            pace_finish = data_date + timedelta(days=remaining_days)
            result["pace_based_forecast"] = {
                "forecast_finish": pace_finish.date().isoformat(),
                "expected_completion_month": pace_finish.strftime("%B %Y"),
                "months_remaining": round(remaining_days / 30.4, 1),
                "_basis": f"{pct}% complete over {elapsed_days} days since start; assumes the average "
                          f"pace continues. Early phases are usually slower than construction, so this "
                          f"tends to be conservative (later) than a ramped schedule.",
            }

    # --- Reconcile the two forecasts into a plain-language assessment ---
    p1 = result.get("p6_schedule_forecast")
    p2 = result.get("pace_based_forecast")
    if pct == 0:
        result["assessment"] = ("Project has not started (0% complete) — no actual pace to project from. "
                                "Only the baseline/scheduled plan is available; treat any date as planned, not forecast.")
        confidence = "LOW"
    elif p1 and p2:
        gap = (datetime.fromisoformat(p2["forecast_finish"]) - datetime.fromisoformat(p1["forecast_finish"])).days
        if gap > 45:
            result["assessment"] = (f"Current pace points to completion around {p2['expected_completion_month']}, "
                                    f"about {gap} days LATER than P6's scheduled {p1['expected_completion_month']} — "
                                    f"the schedule may be optimistic given the pace so far.")
            confidence = "MEDIUM"
        elif gap < -45:
            result["assessment"] = (f"Current pace ({p2['expected_completion_month']}) is ahead of P6's schedule "
                                    f"({p1['expected_completion_month']}) — recent progress has accelerated.")
            confidence = "MEDIUM"
        else:
            result["assessment"] = (f"P6 schedule and current pace agree within ~6 weeks "
                                    f"(~{p1['expected_completion_month']}). Forecast is reasonably firm.")
            confidence = "HIGH"
    elif p1:
        result["assessment"] = f"Using P6's scheduled finish ({p1['expected_completion_month']}); insufficient data for an independent pace check."
        confidence = "MEDIUM"
    else:
        result["assessment"] = "Insufficient schedule data to forecast a completion date."
        confidence = "LOW"

    # Data-freshness haircut on confidence
    if data_date:
        days_stale = (datetime.utcnow() - data_date).days
        if days_stale > 45 and confidence == "HIGH":
            confidence = "MEDIUM"
        result["data_age_days"] = days_stale
    result["confidence"] = confidence

    # --- Milestones at risk: not-yet-complete activities whose finish drifts past baseline ---
    at_risk = []
    for a in activities:
        if a.status and 'complet' in a.status.lower():
            continue
        if a.finish_date and a.baseline_finish_date:
            drift = (a.finish_date - a.baseline_finish_date).days
            if drift > 7:
                at_risk.append({
                    "activity": a.name,
                    "drift_days": drift,
                    "baseline_finish": a.baseline_finish_date.date().isoformat(),
                    "forecast_finish": a.finish_date.date().isoformat(),
                    "is_critical": a.total_float is not None and a.total_float <= 0,
                })
    at_risk.sort(key=lambda x: x["drift_days"], reverse=True)
    result["milestones_at_risk"] = at_risk[:8]
    result["milestones_at_risk_count"] = len(at_risk)

    return result


def sim_forecast_activity_finishes(
    db: Session,
    project_id: str,
    period: str = "month",
    target_year: int | None = None,
    target_month: int | None = None,
    limit: int = 25,
) -> dict:
    """Forecast activities scheduled to finish in one calendar month or year.

    The exact target count comes from each activity's current P6 finish date. For unfinished
    in-progress activities, an independent pace projection uses actual progress since start.
    Not-started activities remain schedule-only candidates rather than receiving invented dates.
    """
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    if not p6:
        return {
            "project_id": project_id,
            "has_data": False,
            "error": "Project not found",
        }

    now = datetime.utcnow()
    period = period.strip().lower()
    if period not in {"month", "year"}:
        raise ValueError("period must be 'month' or 'year'.")
    if period == "month":
        if target_year is None and target_month is None:
            target_year, target_month = now.year, now.month
        elif target_year is None or target_month is None:
            raise ValueError("target_year and target_month must be provided together for a month.")
        if target_year < 2000 or target_year > 2100 or target_month < 1 or target_month > 12:
            raise ValueError("Invalid target month.")
        period_start = datetime(target_year, target_month, 1)
        period_end = (
            datetime(target_year + 1, 1, 1)
            if target_month == 12
            else datetime(target_year, target_month + 1, 1)
        )
        period_label = period_start.strftime("%B %Y")
    else:
        if target_month is not None:
            raise ValueError("target_month must be omitted for a yearly forecast.")
        target_year = target_year or now.year
        if target_year < 2000 or target_year > 2100:
            raise ValueError("Invalid target year.")
        period_start = datetime(target_year, 1, 1)
        period_end = datetime(target_year + 1, 1, 1)
        period_label = str(target_year)
    data_as_of = p6.data_date or p6.last_synced_at
    activities = db.query(models.P6Activity).filter(
        models.P6Activity.project_object_id == p6.p6_object_id
    ).all()

    def is_completed(activity) -> bool:
        return bool(activity.status and "complet" in activity.status.lower())

    def in_target(value) -> bool:
        return bool(value and period_start <= value < period_end)

    scheduled = [activity for activity in activities if in_target(activity.finish_date)]
    remaining = [activity for activity in scheduled if not is_completed(activity)]
    confirmed = [activity for activity in scheduled if is_completed(activity)]
    actual_completed_in_period = [
        activity for activity in activities
        if is_completed(activity) and in_target(activity.actual_finish_date)
    ]

    historical_delays = []
    for activity in activities:
        if not is_completed(activity) or not activity.actual_finish_date:
            continue
        comparison_finish = activity.baseline_finish_date or activity.planned_finish_date
        if comparison_finish:
            historical_delays.append((activity.actual_finish_date - comparison_finish).days)
    historical_on_time = sum(1 for delay in historical_delays if delay <= 7)
    historical_on_time_pct = (
        round(historical_on_time * 100 / len(historical_delays), 1)
        if historical_delays else None
    )

    pace_likely = []
    pace_at_risk = []
    schedule_only = []
    details = []
    for activity in scheduled:
        pct = _norm_pct(activity.percent_complete)
        pace_finish = None
        pace_variance_days = None
        bucket = "confirmed_finished" if is_completed(activity) else "schedule_only"
        if not is_completed(activity) and data_as_of and period_end > data_as_of:
            pace_start = activity.actual_start_date
            if pace_start is None and activity.status and "progress" in activity.status.lower():
                pace_start = activity.start_date
            if pace_start and 0 < pct < 100 and data_as_of > pace_start:
                elapsed_days = max((data_as_of - pace_start).total_seconds() / 86_400, 1.0)
                remaining_days = elapsed_days * (100.0 - pct) / pct
                pace_finish = data_as_of + timedelta(days=remaining_days)
                pace_variance_days = (
                    round((pace_finish - activity.finish_date).total_seconds() / 86_400, 1)
                    if activity.finish_date else None
                )
                if pace_finish < period_end:
                    bucket = "pace_supported_likely_by_period_end"
                    pace_likely.append(activity)
                else:
                    bucket = "pace_at_risk_beyond_period_end"
                    pace_at_risk.append(activity)
            else:
                schedule_only.append(activity)
        elif not is_completed(activity):
            schedule_only.append(activity)

        baseline_drift_days = (
            (activity.finish_date - activity.baseline_finish_date).days
            if activity.finish_date and activity.baseline_finish_date else None
        )
        details.append({
            "activity_id": activity.activity_id,
            "name": activity.name,
            "wbs_name": activity.wbs_name,
            "status": activity.status,
            "percent_complete": pct,
            "current_p6_finish": activity.finish_date.date().isoformat() if activity.finish_date else None,
            "planned_finish": activity.planned_finish_date.date().isoformat() if activity.planned_finish_date else None,
            "baseline_finish": activity.baseline_finish_date.date().isoformat() if activity.baseline_finish_date else None,
            "baseline_drift_days": baseline_drift_days,
            "pace_forecast_finish": pace_finish.date().isoformat() if pace_finish else None,
            "pace_vs_p6_days": pace_variance_days,
            "forecast_bucket": bucket,
            "is_critical": bool(
                activity.is_critical
                or (activity.total_float is not None and activity.total_float <= 0)
            ),
        })

    bucket_order = {
        "pace_at_risk_beyond_period_end": 0,
        "schedule_only": 1,
        "pace_supported_likely_by_period_end": 2,
        "confirmed_finished": 3,
    }
    details.sort(key=lambda item: (
        bucket_order[item["forecast_bucket"]],
        item["current_p6_finish"] or "",
        str(item["activity_id"]),
    ))

    overdue_carry_in = [
        activity for activity in activities
        if not is_completed(activity) and activity.finish_date and activity.finish_date < period_start
    ]
    overdue_as_of_data_date = [
        activity for activity in activities
        if data_as_of and not is_completed(activity)
        and activity.finish_date and activity.finish_date < data_as_of
    ]
    critical_due = [
        activity for activity in remaining
        if activity.is_critical or (activity.total_float is not None and activity.total_float <= 0)
    ]
    drifted_due = [
        activity for activity in remaining
        if activity.baseline_finish_date
        and activity.finish_date
        and (activity.finish_date - activity.baseline_finish_date).days > 7
    ]

    remaining_count = len(remaining)
    pace_coverage_pct = (
        round((len(pace_likely) + len(pace_at_risk)) * 100 / remaining_count, 1)
        if remaining_count else 100.0
    )
    data_age_days = max((now - data_as_of).days, 0) if data_as_of else None
    if data_age_days is None or data_age_days > 30 or pace_coverage_pct < 25:
        confidence = "LOW"
    elif data_age_days <= 14 and pace_coverage_pct >= 60 and len(historical_delays) >= 10:
        confidence = "HIGH"
    else:
        confidence = "MEDIUM"

    scheduled_count = len(scheduled)
    likely_minimum = len(confirmed) + len(pace_likely)
    possible_maximum = max(likely_minimum, scheduled_count - len(pace_at_risk))
    at_risk_ratio = len(pace_at_risk) / remaining_count if remaining_count else 0
    if at_risk_ratio >= 0.3 or (
        historical_on_time_pct is not None
        and len(historical_delays) >= 10
        and historical_on_time_pct < 50
    ):
        outlook = "HIGH_RISK"
    elif pace_at_risk or overdue_carry_in or drifted_due:
        outlook = "AT_RISK"
    else:
        outlook = "ON_PLAN"

    from engine.tools.portfolio_tools import get_project_display_name
    return {
        "project_id": project_id,
        "project_name": get_project_display_name(db, project_id),
        "has_data": True,
        "target_period": {
            "type": period,
            "year": target_year,
            "month": target_month if period == "month" else None,
            "label": period_label,
            "start": period_start.date().isoformat(),
            "end_exclusive": period_end.date().isoformat(),
        },
        "definition": (
            "Scheduled count uses activities whose current P6 finish_date falls in the target period."
        ),
        "data_as_of": data_as_of.date().isoformat() if data_as_of else None,
        "last_synced_at": p6.last_synced_at.isoformat() if p6.last_synced_at else None,
        "data_age_days": data_age_days,
        "p6_schedule_target": {
            "scheduled_to_finish": scheduled_count,
            "confirmed_finished_in_cohort": len(confirmed),
            "remaining_scheduled": remaining_count,
            "actual_finishes_in_period": len(actual_completed_in_period),
            "in_progress": sum(
                1 for activity in remaining
                if activity.status and "progress" in activity.status.lower()
            ),
            "not_started": sum(
                1 for activity in remaining
                if activity.status and "not started" in activity.status.lower()
            ),
        },
        "prediction": {
            "likely_finish_range_by_period_end": {
                "minimum_evidence_supported": likely_minimum,
                "maximum_if_schedule_only_candidates_hold": possible_maximum,
            },
            "pace_supported_likely": len(pace_likely),
            "pace_at_risk": len(pace_at_risk),
            "schedule_only_candidates": len(schedule_only),
            "pace_coverage_pct_of_remaining": pace_coverage_pct,
            "outlook": outlook,
            "confidence": confidence,
            "method": (
                "In-progress pace = elapsed days since actual/current start divided by percent "
                "complete; not-started or insufficient-progress activities retain only their P6 date."
            ),
        },
        "schedule_pressure": {
            "overdue_carry_in_before_period": len(overdue_carry_in),
            "overdue_as_of_data_date": len(overdue_as_of_data_date),
            "critical_remaining_due": len(critical_due),
            "remaining_drifted_over_7_days_vs_baseline": len(drifted_due),
        },
        "historical_delivery": {
            "completed_sample": len(historical_delays),
            "on_time_within_7_days_pct": historical_on_time_pct,
            "median_finish_variance_days": (
                round(float(median(historical_delays)), 1) if historical_delays else None
            ),
            "comparison_basis": "Actual finish versus baseline finish, falling back to planned finish.",
        },
        "returned": min(len(details), limit),
        "total_scheduled": scheduled_count,
        "activities": details[:limit],
        "_source_table": "p6_project, p6_activity",
        "_limitations": (
            "The pace projection is deterministic, not a trained ML probability. It does not model "
            "future resource changes, dependencies, calendars, weather, or unrecorded constraints."
        ),
    }

