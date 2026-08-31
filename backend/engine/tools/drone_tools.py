"""
Akasha AI Agent Tool — Drone Verification

Provides the AI chatbot agent with the ability to query Spectra drone data
to verify DPR-reported progress against ground truth.

Tool: drone_get_verification
  - Fetches live Spectra drone data for a project
  - Compares against P6 claimed progress
  - Returns block-level DPR vs Drone variance
"""

import logging
import asyncio
from datetime import date
from typing import Optional

from services.spectra_service import (
    resolve_spectra_project_id,
    resolve_khavda_block,
    fetch_all_drone_data,
    get_drone_summary,
    ACTIVITY_DRONE_MAP,
)

logger = logging.getLogger(__name__)


DRONE_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "drone_get_verification",
        "description": (
            "Fetch live drone survey data from the Spectra API to verify "
            "DPR-reported construction progress against ground truth. "
            "Returns block-level actual counts for piling, MMS erection, "
            "module installation, inverters, AC works, and robotics. "
            "Use this tool when you need to verify whether reported progress "
            "is accurate or over-reported. Available for Baiya, Khavda (4 sub-projects), "
            "and Bandha projects only."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "The project name (e.g. 'Khavda 200MW', 'Baiya', 'Bandha')"
                },
                "project_id": {
                    "type": "string",
                    "description": "The P6 project ID (e.g. 'FY25-P11')"
                },
                "report_date": {
                    "type": "string",
                    "description": "Date for drone data in YYYY-MM-DD format. Defaults to today."
                },
            },
            "required": ["project_name"],
        },
    },
}


def drone_get_verification(project_name: str, project_id: str = "",
                            report_date: Optional[str] = None) -> dict:
    """
    AI Agent tool: fetch and summarize drone verification data.
    """
    spectra_id = resolve_spectra_project_id(project_name, project_id)
    if spectra_id is None:
        return {
            "status": "unsupported",
            "message": (
                f"Drone verification is not available for '{project_name}'. "
                f"Only Baiya, Khavda (50MW/200MW/167MW/333MW), and Bandha are supported."
            ),
        }

    target_block = None
    if spectra_id == 2:
        target_block = resolve_khavda_block(project_id, project_name)

    if not report_date:
        report_date = date.today().isoformat()

    # Fetch drone data (async → sync bridge)
    try:
        drone_data = asyncio.run(fetch_all_drone_data(spectra_id, report_date))
    except RuntimeError:
        # Already in an async loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            drone_data = pool.submit(
                asyncio.run,
                fetch_all_drone_data(spectra_id, report_date)
            ).result(timeout=45)

    if not drone_data:
        return {
            "status": "no_data",
            "message": f"No drone data available for {project_name} on {report_date}",
        }

    summary = get_drone_summary(drone_data, target_block)

    if not summary:
        return {
            "status": "no_data",
            "message": f"Spectra API returned data but no matching activities found for {report_date}",
        }

    # Format for the AI agent
    activities = []
    for label, data in summary.items():
        activities.append({
            "activity": label,
            "drone_actual": data["drone_actual"],
            "drone_scope": data["drone_scope"],
            "completion_pct": data["completion_pct"],
        })

    project_label = "Khavda" if spectra_id == 2 else ("Baiya" if spectra_id == 1 else "Bandha")
    if target_block:
        project_label += f" ({target_block})"

    return {
        "status": "success",
        "project": project_label,
        "spectra_project_id": spectra_id,
        "report_date": report_date,
        "target_block": target_block,
        "total_activities": len(activities),
        "activities": activities,
        "note": (
            "These are drone-verified actual counts from Spectra surveys. "
            "Compare against P6 or DPR claimed progress to detect over-reporting."
        ),
    }
