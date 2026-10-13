"""Client for the AI prediction service (the separate FastAPI model service the
Ordering Schedule Beta's AI panels call: POST /api/ai/v1/order-tc-forecast).

Advanced planning asks it first, per project, for the recommended order
date, predicted TC and projected FTC; when it cannot answer - not
configured, offline, slow, or an unusable reply - the measured engine
(services/advanced_planning.py) is the fallback, and every figure says
which one it came from.

    AI_PREDICT_URL=https://<host>/api/ai/v1     (backend/.env)

Calls are cached for an hour (same inputs, same answer). The first failure
stops the rest of that build - one dead service must not cost 49 timeouts.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

TIMEOUT_S = 8
CACHE_SECONDS = 3600
WORKERS = 6
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def base_url() -> Optional[str]:
    url = (os.getenv("AI_PREDICT_URL") or "").strip().rstrip("/")
    return url or None


def to_iso(v: Any) -> Optional[str]:
    """ISO date from the schedule's dd-Mon-yy / dd-Mon-yyyy / ISO strings."""
    if not v:
        return None
    if isinstance(v, (date, datetime)):
        return (v.date() if isinstance(v, datetime) else v).isoformat()
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:11] if fmt != "%Y-%m-%d" else s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _call(url: str, body: Dict[str, Any]) -> Dict[str, Any]:
    key = hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    r = requests.post(f"{url}/order-tc-forecast", params={"explain": "true"}, json=body, timeout=TIMEOUT_S,
                      headers={"Accept": "application/json", "ngrok-skip-browser-warning": "true"})
    r.raise_for_status()
    out = r.json()
    if not isinstance(out, dict) or not (out.get("recommended_order_date") or out.get("order_by_date")
                                         or out.get("projected_ftc_date") or out.get("predicted_tc_date")):
        raise ValueError("reply carries no dates")
    _cache[key] = (time.time(), out)
    return out


def _shape(out: Dict[str, Any]) -> Dict[str, Any]:
    ex = out.get("explanation") or {}
    return {
        "order_by": to_iso(out.get("recommended_order_date") or out.get("order_by_date")),
        "tc": to_iso(out.get("predicted_tc_date")),
        "tc_p90": to_iso(out.get("predicted_tc_date_p90")),
        "ftc": to_iso(out.get("projected_ftc_date")),
        "confidence": out.get("confidence"),
        "risk": out.get("risk_level"),
        "deadline_breach_days": out.get("deadline_breach_days"),
        "summary": ex.get("executive_summary") or ex.get("text"),
        "drivers": ex.get("key_drivers") or [],
        "actions": ex.get("recommended_actions") or [],
    }


def predict(requests_by_pid: Dict[str, Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], str]:
    """{project_id: prediction} for the projects the service answered, and a
    status line for the screen."""
    url = base_url()
    if not url:
        return {}, "AI service not configured (AI_PREDICT_URL)"
    items = list(requests_by_pid.items())
    if not items:
        return {}, "AI service: nothing to ask"
    out: Dict[str, Dict[str, Any]] = {}
    # One probe first: a dead service fails once, not once per project.
    pid0, body0 = items[0]
    try:
        out[pid0] = _shape(_call(url, body0))
    except Exception as e:
        logger.warning("AI prediction service unavailable, measured engine used: %s", e)
        reason = "offline" if isinstance(e, (requests.ConnectionError, requests.Timeout)) else "no usable answer"
        if isinstance(e, requests.HTTPError) and e.response is not None:
            reason = ("offline (tunnel down)" if "ngrok" in (e.response.text or "").lower()
                      else f"returned {e.response.status_code}")
        return {}, f"AI service {reason}"

    def one(item):
        pid, body = item
        try:
            return pid, _shape(_call(url, body))
        except Exception as e:      # this project only
            logger.info("AI prediction failed for %s: %s", pid, e)
            return pid, None

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for pid, res in pool.map(one, items[1:]):
            if res:
                out[pid] = res
    return out, f"AI service answered {len(out)} of {len(items)} projects"


def request_for(project: Dict[str, Any], rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The service's input for one project, from the schedule's own figures
    and the next open FTC phase. None when there is no FTC to forecast."""
    nxt = next((ph for ph in (project.get("phases") or []) if not ph.get("charged") and ph.get("ftc")), None)
    if not nxt:
        return None
    s = project.get("supply") or {}
    lta = min(filter(None, (to_iso(r.get("lta")) for r in rows)), default=None)
    scod = min(filter(None, (to_iso(r.get("scod")) for r in rows)), default=None)
    return {
        "project_id": project["project_id"],
        "project_name": project.get("p6_name") or project.get("project_name") or project["project_id"],
        "phase": nxt["name"],
        "vendor_type": project.get("origin") or "ALMM",
        "priority": (rows[0].get("priority") or "standard"),
        "capacity_mwp": round(sum(r.get("capacity_mwp") or 0 for r in rows), 1),
        "balance_ordering": round(sum(r.get("balance_ordering_mwp") or 0 for r in rows), 1),
        "inventory": s.get("stock_mwp", 0),
        "receipt": s.get("received_mwp", 0),
        "under_transit": s.get("in_transit_mwp", 0),
        "lta_date": lta or nxt["ftc"],
        "scod_date": scod or nxt["ftc"],
        "ftc_date": nxt["ftc"],
    }
