"""Ordering Schedule BETA - endpoints used only by the Beta page
(frontend/src/features/modules_beta), kept apart from the live
routers/module_deliveries.py so the live Ordering Schedule is untouched.

The Beta page reads the live /api/module-deliveries/summary as-is; the AI
results, the AI-service proxy and Advanced AI planning below are Beta-specific."""
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
from routers.module_deliveries import get_module_deliveries_summary

from fastapi import Depends as _Depends
from services.demo_scope import see_demo

# Module Ordering: demo projects are visible here (services/demo_scope.py).
router = APIRouter(prefix="/api/module-deliveries-beta", tags=["Module Deliveries (Beta)"], dependencies=[_Depends(see_demo)])


# ── AI results ────────────────────────────────────────────────────────────────
# The AI team scores every project offline (UC1 order-tc-forecast, UC2
# priority-predict) and ships the results as an export of /summary with two
# fields added per project: ai_monthly_order_tc_forecast and ai_priority. The
# Beta page keeps reading the LIVE /summary and merges these in by project id,
# so a stale export never replaces live SAP/P6 figures - it only adds the AI
# view. Re-read automatically when the file changes; AI_RESULTS_FILE overrides
# the location.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Newest export first (the governed export, with the governance review fields);
# the earlier exports stay as fallbacks.
AI_RESULTS_FILE = os.getenv("AI_RESULTS_FILE") or next(
    (p for p in (os.path.join(_BACKEND_DIR, n) for n in (
        "AIAkashaOrderingSchedule_governed.json", "sampleop.json", "AIAkashaOrderingSchedule_final.json"))
     if os.path.isfile(p)),
    os.path.join(_BACKEND_DIR, "AIAkashaOrderingSchedule_governed.json"),
)
_ai_results_cache: dict = {"mtime": None, "data": None}


@router.get("/ai-results")
def get_ai_results(portfolio: Optional[str] = None, db: Session = Depends(get_db)):
    """AI results per dashboard row, keyed by project_mapping id."""
    from routers.module_deliveries import scope_ai_results
    return scope_ai_results(_load_ai_results(), portfolio, db)


def _load_ai_results() -> dict:
    path = AI_RESULTS_FILE
    if not os.path.isfile(path):
        return {"available": False, "reason": "AI results file not found on the server", "meta": None, "by_id": {}}
    mtime = os.path.getmtime(path)
    if _ai_results_cache["mtime"] != mtime:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        by_id = {}
        for p in (doc.get("ordering_schedule") or {}).get("projects") or []:
            if p.get("id") is None:
                continue
            by_id[str(p["id"])] = {
                # Carried so the page can refuse a row whose id now points at a
                # different project than the one the AI scored.
                "p6_name": p.get("p6_name"),
                # With p6_name, these let the page match a row when it runs
                # against a database whose ids differ from the export's (UAT).
                "plot": p.get("plot"),
                "project_name": p.get("project_name"),
                "ai_priority": p.get("ai_priority"),
                "ai_monthly_order_tc_forecast": p.get("ai_monthly_order_tc_forecast"),
                # Governance review of the two AI answers: VALIDATED / CORRECTED,
                # why, and each field it changed (before -> after).
                "ai_review_status": p.get("ai_review_status"),
                "ai_review_reason": p.get("ai_review_reason"),
                "ai_review_changes": p.get("ai_review_changes") or [],
            }
        _ai_results_cache.update(mtime=mtime, data={
            "available": True,
            "meta": (doc.get("meta") or {}).get("ai"),
            "by_id": by_id,
        })
    return _ai_results_cache["data"]


# ── AI prediction service (Ordering_Schedule_AI) ─────────────────────────────
# The Beta's prediction panels call the separate AI service (FastAPI, port
# 8000). The browser cannot reach it directly on the server, so its requests
# come here - under /akasha/api, behind the same login as the rest of Akasha -
# and are passed on unchanged. AI_SERVICE_URL points at the service's /api/ai/v1.
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://localhost:8000/api/ai/v1").rstrip("/")


@router.api_route("/ai-proxy/{path:path}", methods=["GET", "POST"])
async def ai_proxy(path: str, request: Request):
    """Forward a prediction request to the AI service and return its answer."""
    import httpx
    url = f"{AI_SERVICE_URL}/{path}"
    try:
        # The explanation is written by an LLM, which can take a while.
        async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
            r = await client.request(
                request.method, url, params=request.query_params,
                content=await request.body(),
                headers={"Content-Type": request.headers.get("content-type", "application/json")},
            )
    except httpx.HTTPError as e:
        return Response(
            content=json.dumps({"detail": f"The AI service is not reachable at {AI_SERVICE_URL} "
                                          f"({type(e).__name__}). Start it: python -m uvicorn "
                                          f"service.app:app --port 8000 in Ordering_Schedule_AI."}),
            status_code=502, media_type="application/json")
    return Response(content=r.content, status_code=r.status_code,
                    media_type=r.headers.get("content-type", "application/json"))


@router.get("/advanced-plan")
def get_advanced_plan(portfolio: Optional[str] = None, db: Session = Depends(get_db)):
    """Advanced AI planning (from branch orderingpoc), shown on the Beta's
    "Advanced AI planning" tab: block-by-block module need from each block's
    stage progress (piling -> capping -> structure -> purlin -> modules),
    grouped by FTC phase, netted against the Ordering Schedule's own supply
    figures. See services/advanced_planning.py."""
    from services import advanced_planning
    # Same projects the user can see on the Ordering Schedule (?portfolio=).
    summary = get_module_deliveries_summary(scenario="baseline", priorities=None,
                                            portfolio=portfolio, phase=None, db=db)
    pid_of = {mid: pid for mid, pid in db.execute(
        text("select id, project_id from project_mapping where project_id is not null"))}
    rows = [{**p, "project_id": pid_of.get(p["id"])} for p in summary["projects"]]
    return advanced_planning.build(db, rows)
