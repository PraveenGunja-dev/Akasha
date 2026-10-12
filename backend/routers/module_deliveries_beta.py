"""Ordering Schedule BETA - endpoints used only by the Beta page
(frontend/src/features/modules_beta), kept apart from the live
routers/module_deliveries.py so the live Ordering Schedule is untouched.

The Beta page reads the live /api/module-deliveries/summary as-is; only the
block-level plan below is Beta-specific."""
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from routers.module_deliveries import get_module_deliveries_summary

router = APIRouter(prefix="/api/module-deliveries-beta", tags=["Module Deliveries (Beta)"])


@router.get("/block-plan")
def get_block_level_plan(
    portfolio: Optional[str] = None,
    phase: Optional[str] = "ongoing",
    buffer_days: int = 15,
    db: Session = Depends(get_db),
):
    """Construction-level (block-by-block) module ordering plan
    (services/block_ordering.py): each block's P6 Module Installation window,
    held back by its MMS erection and checked against SCOD / LTA, netted
    against SAP's module pipeline and moved back by supplier lead time.
    Same projects and SAP figures as /api/module-deliveries/summary."""
    from services.block_ordering import build_block_plan
    summary = get_module_deliveries_summary(scenario="baseline", priorities=None,
                                            portfolio=portfolio, phase=phase, db=db)
    return build_block_plan(db, summary.get("projects") or [], buffer_days=buffer_days)


class BlockPlanExplainRequest(BaseModel):
    """What to explain: the whole plan, or one project of it. The page sends
    back the plan it is showing, so the words match the screen exactly."""
    scope: str = "portfolio"            # portfolio | project
    plan: Optional[dict] = None
    project: Optional[dict] = None


@router.post("/block-plan/explain")
def explain_block_plan(req: BlockPlanExplainRequest):
    """Plain-language explanation of the block plan (services/block_plan_ai.py):
    written by the AI model from the plan's own figures, or by a fixed template
    when no model is reachable."""
    from services.block_plan_ai import explain_portfolio, explain_project
    if req.scope == "project" and req.project:
        return explain_project(req.project)
    return explain_portfolio(req.plan or {})


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
def get_ai_results():
    """AI results per dashboard row, keyed by project_mapping id."""
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
