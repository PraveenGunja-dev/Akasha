"""
Akasha Platform — Spectra Drone Service

Connects to the Spectra Insights API to fetch live drone survey data
for DPR vs Drone verification. Ported from the Digitalized_DPR_Prod workspace.

Supports:
  - Baiya (Spectra project_id = 1)
  - Khavda (Spectra project_id = 2) with 4 sub-projects (A16A/B/C/D)
  - Bandha (Spectra project_id = 3)

Read-only: never modifies existing data.
"""

import os
import re
import logging
import httpx
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

SPECTRA_BASE_URL = os.getenv("SPECTRA_BASE_URL", "https://dpr.spectra-insights.com/api")
SPECTRA_API_KEY = os.getenv("SPECTRA_API_KEY", "")


def _auth_headers() -> Dict[str, str]:
    """Spectra takes the key as a header, never as a query parameter.

    Sending ?api_key= returns 401 with the API's own hint:
        "Missing API key. Use X-API-Key or Authorization: Bearer <key>."
    Every call was failing this way, and the failure was swallowed into an
    empty result that looked identical to "no flights yet".
    """
    return {"X-API-Key": SPECTRA_API_KEY} if SPECTRA_API_KEY else {}


# ══════════════════════════════════════════════════════════════
# Project Resolution
# ══════════════════════════════════════════════════════════════

# Spectra surveys three sites, and Khavda is split into exactly four blocks.
# These are enumerated rather than inferred: the previous heuristics matched
# "50MW" anywhere in a name and treated any FY25-P1x id as Khavda, which pulled
# three unsurveyed projects in — A10a and A15a were both reported as block A16A,
# and A06 was invented as a fifth Khavda block.
KHAVDA_BLOCKS = {
    "FY25-P10": "A16A",
    "FY25-P11": "A16B",
    "FY25-P12": "A16C",
    "FY25-P13": "A16D",
}


def resolve_spectra_project_id(project_name: str, p6_id: Optional[str] = None) -> Optional[int]:
    """Map an Akasha project to its Spectra project_id, or None if not surveyed.

    Only three sites are flown, so anything else must return None — a wrong id
    reports another site's drone progress against this project.
    """
    name_lower = (project_name or "").lower()

    # NHPC Khavda is a different asset from the AGEL Khavda blocks and is not
    # surveyed; check it before the Khavda test below.
    if "nhpc" in name_lower:
        return None

    if "baiya" in name_lower:
        return 1
    if "bandha" in name_lower:
        return 3
    if p6_id in KHAVDA_BLOCKS:
        return 2

    return None


def resolve_khavda_block(p6_id: str, p6_name: str) -> Optional[str]:
    """Which of the four Khavda blocks a project is, or None.

    No fuzzy fallback. A project that is not one of the four is not surveyed,
    and guessing a block name from the project title produced blocks that do
    not exist in Spectra.
    """
    return KHAVDA_BLOCKS.get(p6_id or "")


# ══════════════════════════════════════════════════════════════
# Activity-to-Spectra-API mapping (from drone_verification.py)
# ══════════════════════════════════════════════════════════════

ACTIVITY_DRONE_MAP = [
    # --- block_progress API ---
    {"pattern": r"piling\s*-?\s*mms|piling.*marking.*auguring|marking.*auguring.*concreting",
     "api": "block_progress", "field": "piling_total", "actual_field": "piling_current", "label": "Piling - MMS"},
    {"pattern": r"pile\s*capp",
     "api": "block_progress", "field": "piling_cap_total", "actual_field": "piling_cap_current", "label": "Pile Capping"},
    {"pattern": r"mms\s*erection.*torque\s*tube|torque\s*tube.*raft[ae]r",
     "api": "block_progress", "field": "rafter_total", "actual_field": "rafter_current", "label": "MMS Erection - Torque Tube/Raftar"},
    {"pattern": r"mms\s*erection.*purlin|purlin",
     "api": "block_progress", "field": "purlin_total", "actual_field": "purlin_current", "label": "MMS Erection - Purlin"},
    {"pattern": r"module\s*(installation|mounting)",
     "api": "block_progress", "field": "module_total", "actual_field": "module_current", "label": "Module Installation"},

    # --- inverter_progress API ---
    {"pattern": r"piling\s*-?\s*inverter",
     "api": "inverter_progress", "field": "count_piling", "actual_field": "count_piling", "label": "Piling - Inverters"},
    {"pattern": r"inverter\s*installation",
     "api": "inverter_progress", "field": "total_inverters", "actual_field": "count_inverter_completed", "label": "Inverter Installation"},

    # --- robot_progress API ---
    {"pattern": r"piling\s*-?\s*robotic\s*docking",
     "api": "robot_progress", "field": "count_piling", "actual_field": "count_piling", "label": "Piling - Robotic Docking System"},
    {"pattern": r"robotic\s*structure\s*-?\s*docking\s*station",
     "api": "robot_progress", "field": "count_robot_installed", "actual_field": "count_robot_installed", "label": "Robotic Structure - Docking Station"},
    {"pattern": r"robot\s*installation",
     "api": "robot_progress", "field": "count_robot_installed", "actual_field": "count_robot_installed", "label": "Robot Installation"},

    # --- ac_work_progress API ---
    {"pattern": r"ht\s*&?\s*lt\s*station\s*-?\s*slab",
     "api": "ac_work_progress", "field": "ht_lt_station_slab", "actual_field": "ht_lt_station_slab", "label": "HT & LT Station - Slab"},
    {"pattern": r"idt\s*foundation.*grade\s*slab|grade\s*slab.*dyke",
     "api": "ac_work_progress", "field": "idt_foundation_grad_slab_dyke", "actual_field": "idt_foundation_grad_slab_dyke", "label": "IDT Foundation - Grade Slab & Dyke Wall"},
    {"pattern": r"nifps\s*foundation",
     "api": "ac_work_progress", "field": "nifps_foundation", "actual_field": "nifps_foundation", "label": "NIFPS Foundation"},
    {"pattern": r"idt\s*erection",
     "api": "ac_work_progress", "field": "idt_erection", "actual_field": "idt_erection", "label": "IDT Erection"},
    {"pattern": r"ht\s*panel\s*erection",
     "api": "ac_work_progress", "field": "ht_panel_erection", "actual_field": "ht_panel_erection", "label": "HT Panel Erection"},
    {"pattern": r"lt\s*panel\s*erection",
     "api": "ac_work_progress", "field": "lt_panel_erection", "actual_field": "lt_panel_erection", "label": "LT Panel Erection"},
]


# ══════════════════════════════════════════════════════════════
# Spectra API Communication
# ══════════════════════════════════════════════════════════════

# robot_block_progress was missing, so per-block robot data was never fetched.
SPECTRA_APIS = [
    "block_progress",
    "inverter_progress",
    "robot_progress",
    "robot_block_progress",
    "ac_work_progress",
]


async def _fetch_spectra_endpoint(client: httpx.AsyncClient, api_name: str,
                                   project_id: int, report_date: str) -> Dict[str, Any]:
    """Fetch a single Spectra API endpoint."""
    url = f"{SPECTRA_BASE_URL}/{api_name}"
    # The parameter is `date`. Sending `report_date` returns 422:
    #   "Provide either 'date' or both 'start_date' and 'end_date'."
    params = {"project_id": project_id, "date": report_date}
    try:
        resp = await client.get(url, params=params, headers=_auth_headers(), timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        return {"rows": data if isinstance(data, list) else data.get("data", data.get("rows", [])), "status": "ok"}
    except httpx.HTTPStatusError as e:
        logger.warning(f"Spectra {api_name} returned {e.response.status_code} for project {project_id}")
        return {"rows": [], "status": f"error_{e.response.status_code}"}
    except Exception as e:
        logger.error(f"Spectra {api_name} failed: {e}")
        return {"rows": [], "status": "error"}


async def fetch_all_drone_data(project_id: int, report_date: str = None) -> Dict[str, Any]:
    """Fetch every Spectra dataset for a project.

    Each dataset is flown on its own schedule — for Khavda, block_progress was
    last flown 2026-06-25 but ac_work_progress 2026-06-02 — so a single shared
    report_date returns nothing for whichever datasets were not flown that day.
    The available dates are therefore read first and each dataset uses its own
    most recent one. Pass `report_date` to pin them all to a specific day.
    """
    if not SPECTRA_API_KEY:
        logger.warning("SPECTRA_API_KEY not set — skipping drone fetch")
        return {"status": "no_api_key"}

    calendar = {} if report_date else await fetch_available_dates(project_id)

    async with httpx.AsyncClient(verify=False) as client:
        results = {}
        for api_name in SPECTRA_APIS:
            if report_date:
                use_date = report_date
            else:
                dates = calendar.get(api_name) or []
                use_date = dates[-1] if dates else None
            if not use_date:
                results[api_name] = {"rows": [], "status": "no_flights"}
                continue
            fetched = await _fetch_spectra_endpoint(client, api_name, project_id, use_date)
            fetched["report_date"] = use_date
            results[api_name] = fetched
        return results


async def fetch_available_dates(project_id: int) -> Dict[str, Any]:
    """Flight dates per dataset, oldest first.

    Shape: {"block_progress": ["2025-12-22", ...], "ac_work_progress": [...], ...}
    An empty list means that dataset has never been flown for this project —
    Baiya and Bandha have no robot data at all, for instance.
    """
    if not SPECTRA_API_KEY:
        return {}

    url = f"{SPECTRA_BASE_URL}/available_dates"
    try:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                url,
                params={"project_id": project_id},
                headers=_auth_headers(),
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}
    except httpx.HTTPStatusError as e:
        # Surfaced rather than swallowed: a 401 here is an expired key, which
        # is a very different problem from "no flights yet".
        logger.error(
            "Spectra available_dates returned %s for project %s — %s",
            e.response.status_code, project_id, e.response.text[:120],
        )
        return {}
    except Exception as e:
        logger.error("Spectra available_dates failed for project %s: %s", project_id, e)
        return {}


def aggregate_spectra_data(api_rows: List[Dict], field: str,
                            target_block_prefix: Optional[str] = None) -> float:
    """Sum a specific field from Spectra API rows, optionally filtered by block prefix."""
    total = 0.0
    for row in api_rows:
        if target_block_prefix:
            row_block = row.get("block_name") or row.get("block") or ""
            if not str(row_block).upper().startswith(target_block_prefix):
                continue
        val = row.get(field)
        if val is not None:
            try:
                total += float(val)
            except (ValueError, TypeError):
                pass
    return total


def get_drone_summary(drone_data: Dict[str, Any],
                       target_block_prefix: Optional[str] = None) -> Dict[str, Any]:
    """
    Produce a summary of drone-verified progress across all activities.
    Returns per-activity totals for use by drone_intel.py.
    """
    summary = {}
    for mapping in ACTIVITY_DRONE_MAP:
        api_name = mapping["api"]
        actual_field = mapping.get("actual_field") or mapping["field"]
        scope_field = mapping["field"]
        label = mapping["label"]

        api_data = drone_data.get(api_name, {})
        rows = api_data.get("rows", []) if isinstance(api_data, dict) else []

        drone_actual = aggregate_spectra_data(rows, actual_field, target_block_prefix)
        drone_scope = aggregate_spectra_data(rows, scope_field, target_block_prefix)

        if drone_actual > 0 or drone_scope > 0:
            summary[label] = {
                "api": api_name,
                "drone_actual": round(drone_actual, 2),
                "drone_scope": round(drone_scope, 2),
                "completion_pct": round(drone_actual / max(drone_scope, 1) * 100, 1),
            }

    return summary
