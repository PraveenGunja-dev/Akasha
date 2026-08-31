"""
Akasha Intelligence Engine — Drone / Ground Truth Intelligence

Compares P6 claimed progress against Spectra drone-verified actuals to:
- Detect DPR over-reporting or under-reporting
- Produce a health_score (100 = perfect match, 0 = massive discrepancy)
- Flag specific blocks/activities with high variance
- Generate insights for cross-domain correlation in risk_intel.py

Read-only: never modifies existing data.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from services.spectra_service import (
    resolve_spectra_project_id,
    resolve_khavda_block,
    fetch_all_drone_data,
    get_drone_summary,
)

logger = logging.getLogger(__name__)


def analyze_drone(ctx: dict) -> dict:
    """
    Drone / Ground Truth intelligence analysis for a project.

    Fetches live Spectra drone data, compares against P6 progress claims,
    and produces a health score and variance report.
    """
    project_name = ctx["project_name"]
    project_id = ctx.get("project_id", "")
    p6_project = ctx.get("p6_project")

    # ═══════════════════════════════════════════════════════
    # 1. RESOLVE SPECTRA PROJECT
    # ═══════════════════════════════════════════════════════
    spectra_id = resolve_spectra_project_id(project_name, project_id)

    if spectra_id is None:
        return {
            "has_data": False,
            "health_score": None,
            "supported": False,
            "insights": [{
                "severity": "info",
                "domain": "drone",
                "title": f"Drone verification not available for {project_name}",
                "description": "This project is not mapped to a Spectra drone project (only Baiya, Khavda, Bandha supported).",
                "impact": "Ground truth verification unavailable — DPR progress unverified",
            }],
            "next_steps": [],
        }

    # Resolve Khavda block prefix if applicable
    target_block = None
    if spectra_id == 2:
        target_block = resolve_khavda_block(project_id, project_name)

    # ═══════════════════════════════════════════════════════
    # 2. FETCH DRONE DATA (async → sync bridge)
    # ═══════════════════════════════════════════════════════
    # No report_date: each Spectra dataset is flown on its own schedule, so
    # fetch_all_drone_data resolves the most recent flight per dataset. Passing
    # today's date — as this did — asked for a day nothing was flown on and
    # returned empty every time.
    try:
        # Always run the coroutine on a dedicated thread with its own loop.
        # asyncio.get_event_loop() raises "There is no current event loop" when
        # a sync FastAPI handler runs in an AnyIO worker thread, which is
        # exactly where this executes.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            drone_data = pool.submit(
                lambda: asyncio.run(fetch_all_drone_data(spectra_id))
            ).result(timeout=60)

        # The dates actually flown, per dataset — used for provenance below.
        flight_dates = {
            api: res.get("report_date")
            for api, res in (drone_data or {}).items()
            if isinstance(res, dict) and res.get("report_date")
        }
        report_date = max(flight_dates.values()) if flight_dates else None
    except Exception as e:
        logger.error(f"Failed to fetch drone data for {project_name}: {e}")
        return {
            "has_data": False,
            "health_score": None,
            "supported": True,
            "insights": [{
                "severity": "medium",
                "domain": "drone",
                "title": f"Drone data fetch failed for {project_name}",
                "description": f"Could not reach Spectra API: {str(e)}",
                "impact": "Ground truth verification temporarily unavailable",
            }],
            "next_steps": [],
        }

    # Check if we got any meaningful data
    apis_with_data = sum(
        1 for v in drone_data.values()
        if isinstance(v, dict) and v.get("rows")
    )
    if apis_with_data == 0:
        return {
            "has_data": False,
            "health_score": None,
            "supported": True,
            "insights": [{
                "severity": "info",
                "domain": "drone",
                "title": f"No drone flight data available for {project_name}",
                "description": "Spectra returned no rows for the most recent flight of any dataset.",
                "impact": "Ground truth verification unavailable for this project",
            }],
            "next_steps": [],
        }

    # ═══════════════════════════════════════════════════════
    # 3. COMPUTE DRONE SUMMARY
    # ═══════════════════════════════════════════════════════
    summary = get_drone_summary(drone_data, target_block)

    if not summary:
        return {
            "has_data": False,
            "health_score": None,
            "supported": True,
            "insights": [],
            "next_steps": [],
        }

    # ═══════════════════════════════════════════════════════
    # 4. COMPARE AGAINST P6 PROGRESS
    # ═══════════════════════════════════════════════════════
    # Compare drone completion % against P6 overall progress
    p6_progress = 0
    if p6_project:
        p6_progress = p6_project.duration_percent_complete or 0
        if p6_progress <= 1:
            p6_progress = p6_progress * 100

    # Weighted average of drone completion across all activities
    total_drone_scope = sum(s["drone_scope"] for s in summary.values())
    total_drone_actual = sum(s["drone_actual"] for s in summary.values())
    drone_overall_pct = round(total_drone_actual / max(total_drone_scope, 1) * 100, 1)

    # Variance = what DPR/P6 claims minus what drone actually shows
    variance_pct = round(p6_progress - drone_overall_pct, 1)

    # ═══════════════════════════════════════════════════════
    # 5. HEALTH SCORE
    # ═══════════════════════════════════════════════════════
    # 100 = perfect match, decreases as variance increases
    abs_variance = abs(variance_pct)
    if abs_variance <= 2:
        health_score = 95
    elif abs_variance <= 5:
        health_score = 80
    elif abs_variance <= 10:
        health_score = 65
    elif abs_variance <= 20:
        health_score = 40
    elif abs_variance <= 30:
        health_score = 20
    else:
        health_score = 5

    # ═══════════════════════════════════════════════════════
    # 6. GENERATE INSIGHTS
    # ═══════════════════════════════════════════════════════
    insights = []

    if variance_pct > 5:
        insights.append({
            "severity": "high" if variance_pct > 15 else "medium",
            "domain": "drone",
            "title": f"DPR progress over-reported by {variance_pct}%",
            "description": (
                f"P6 claims {p6_progress:.1f}% complete, but drone verification shows "
                f"only {drone_overall_pct:.1f}% (variance: +{variance_pct}%)"
            ),
            "impact": "Actual project delay may be worse than reported. Schedule recovery plans based on DPR data are unreliable.",
        })
    elif variance_pct < -5:
        insights.append({
            "severity": "info",
            "domain": "drone",
            "title": f"DPR progress under-reported by {abs(variance_pct)}%",
            "description": (
                f"P6 claims {p6_progress:.1f}% complete, but drone shows "
                f"{drone_overall_pct:.1f}% (variance: {variance_pct}%)"
            ),
            "impact": "Project may be ahead of what DPR reports. P6 schedule may not have been updated.",
        })
    else:
        insights.append({
            "severity": "info",
            "domain": "drone",
            "title": "DPR progress verified by drone",
            "description": (
                f"P6 claims {p6_progress:.1f}% complete, drone confirms "
                f"{drone_overall_pct:.1f}% (variance within ±5%)"
            ),
            "impact": "Ground truth aligns with reported progress — high confidence in schedule data.",
        })

    # Flag individual activities with high variance
    activity_flags = []
    for label, data in summary.items():
        if data["drone_scope"] > 0 and data["completion_pct"] < 50:
            activity_flags.append({
                "activity": label,
                "drone_completion": data["completion_pct"],
                "drone_actual": data["drone_actual"],
                "drone_scope": data["drone_scope"],
            })

    if activity_flags:
        worst = min(activity_flags, key=lambda x: x["drone_completion"])
        insights.append({
            "severity": "medium",
            "domain": "drone",
            "title": f"Activity '{worst['activity']}' lagging at {worst['drone_completion']}%",
            "description": (
                f"Drone shows {worst['drone_actual']}/{worst['drone_scope']} "
                f"completed for {worst['activity']}"
            ),
            "impact": "This activity may be on the critical path — verify with P6 schedule",
        })

    return {
        "has_data": True,
        "health_score": health_score,
        "supported": True,
        "spectra_project_id": spectra_id,
        "target_block": target_block,
        "report_date": report_date,
        "flight_dates": flight_dates,
        "p6_progress_pct": round(p6_progress, 1),
        "drone_progress_pct": drone_overall_pct,
        "variance_pct": variance_pct,
        "activity_summary": summary,
        "activity_flags": activity_flags,
        "insights": insights,
        "next_steps": [],
    }
