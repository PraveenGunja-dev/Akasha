"""LLM governance review over the UC1 / UC2 results (Akasha AI Governance Layer).

The ML result is computed first (the _v1 logic). The LLM then reviews it with
the governance system prompt (src/akasha_system_prompt.txt) against the
project's row in data/raw/Module Deliveries.csv - planning flags from the
Remarks, the FTC / TC / Module date cells, the planner's month-wise plan,
stock and balance - and may correct a short whitelist of fields:

    UC1  order_by_date, predicted_tc_date, predicted_tc_date_p90,
         projected_ftc_date, risk_level
    UC2  priority_class

Corrections are only proposals: service/app.py applies them inside the same
computation, so everything derived from a date (recommended order date,
order_now, root cause, explanation) follows it, and rejects any that break
the planning rules (TC before the order, FTC earlier than TC + 45 d, a PPA
penalty P1 downgraded). What happened is reported in model.llm_review.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from . import explain
from .engine import ROOT  # noqa: I001 - engine puts src/ on the path, so it comes before parsers

import parsers as P  # noqa: E402

PROMPT = (ROOT / "src" / "akasha_system_prompt.txt").read_text(encoding="utf-8")
RISKS = ("LOW", "MEDIUM", "HIGH")
CLASSES = ("P1", "P2", "STANDARD")
UC1_FIELDS = ("order_by_date", "predicted_tc_date", "predicted_tc_date_p90", "projected_ftc_date", "risk_level")

SCOPE = {
    "uc1": """
====================================================
THIS REQUEST (API contract)
====================================================
Review Use Case 1 only; return "ai_priority": {}.
In "ai_monthly_order_tc_forecast" return ONLY the fields you correct, chosen from:
  "order_by_date", "predicted_tc_date", "predicted_tc_date_p90", "projected_ftc_date" (YYYY-MM-DD),
  "risk_level" (LOW / MEDIUM / HIGH).
Return {} and "ai_review_status": "VALIDATED" when the forecast is consistent with the planning data.
Correct only when the Module Deliveries data clearly contradicts the forecast. Keep: order_by_date <=
predicted_tc_date <= predicted_tc_date_p90, and predicted_tc_date + 45 days <= projected_ftc_date.
The AI order-by date is planned from the realistic (site-ready) FTC and the measured supplier lead time; a
later date than the Rule Engine is not by itself an error. Dates must be achievable from Today: an order
cannot be placed in the past, and modules reach site no earlier than the order date plus the lead time
(model.lead_time_p50_days). An FTC the planning flags call unreachable cannot be restored by a correction.
"ai_review_reason": at most 2 sentences, business language, naming the data that drove the decision.""",
    "uc2": """
====================================================
THIS REQUEST (API contract)
====================================================
Review Use Case 2 only; return "ai_monthly_order_tc_forecast": {}.
In "ai_priority" return {"priority_class": "P1" | "P2" | "STANDARD"} ONLY if you correct it, else {}.
Return "ai_review_status": "VALIDATED" when the priority is consistent with the planning data.
A PPA phase that charges after SCOD (and after the LTA) carries the penalty and stays P1.
"ai_review_reason": at most 2 sentences, business language, naming the data that drove the decision.""",
}


@dataclass
class Review:
    status: str                     # VALIDATED / CORRECTED as the LLM returned it
    reason: str
    corrections: dict = field(default_factory=dict)   # field -> typed proposed value
    provider: Optional[str] = None
    source: Optional[str] = None
    malformed: list = field(default_factory=list)      # proposals dropped as invalid values


# ── Module Deliveries.csv context ────────────────────────────────────────────

def _load_md() -> tuple[pd.DataFrame, pd.DataFrame]:
    md, plan = P.parse_module_deliveries(ROOT / "data" / "raw")
    return md, plan


try:
    MD, MD_PLAN = _load_md()
except Exception:  # noqa: BLE001 - the review works without it, and says so
    MD, MD_PLAN = pd.DataFrame(), pd.DataFrame()


def _clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, pd.Timestamp):
        return None if pd.isna(v) else v.date().isoformat()
    if hasattr(v, "item"):
        return v.item()
    return v


def md_row(p6_name: Optional[str], project_name: Optional[str] = None) -> Optional[dict]:
    """The project's Module Deliveries row in planner terms, with its planning flags."""
    if MD.empty:
        return None
    key = re.sub(r"\s+", "", p6_name or "").upper()
    names = MD["p6_name"].fillna("").str.replace(r"\s+", "", regex=True).str.upper()
    hit = MD[(names == key) | names.str.startswith(key + "_")] if key else MD.iloc[0:0]
    if hit.empty and project_name:
        hit = MD[MD["project"].str.strip().str.lower() == project_name.strip().lower()]
    if hit.empty:
        return None
    r = hit.sort_values("capacity_mwp", na_position="first").iloc[-1]   # duplicates: keep the mapped row
    g = lambda c: _clean(r.get(c))  # noqa: E731
    flags = [name for name, on in (
        ("ftc_unreachable", (g("rule_shortfall_days") or 0) > 0),
        ("module_date_passed", bool(g("rule_overdue_order"))),
        ("ftc_past_lta", bool(g("rule_ftc_past_lta"))),
        ("quota_moved", bool(g("rule_quota_pushed"))),
        ("capacity_delayed", bool(g("rule_capacity_delayed_past_lta"))),
        ("records_gap", bool(g("rule_records_gap")))) if on]
    plan = MD_PLAN[MD_PLAN["row_id"] == r["row_id"]] if not MD_PLAN.empty else MD_PLAN
    pct = lambda c: None if g(c) is None else f"{g(c) * 100:.0f}%" if g(c) <= 1 else f"{g(c):.0f}%"  # noqa: E731
    return {
        "Project": g("project"), "P6 Name": g("p6_name"), "EPC": g("epc_group"), "Category": g("category"),
        "Type": g("vendor_type"), "Priority": g("priority"), "OL": g("ol"),
        "Capacity MWac": g("capacity_mwac"), "Capacity MWp": g("capacity_mwp"),
        "LTA": g("lta"), "SCOD": g("scod"), "AOP": g("aop"),
        "Ordered MWp": g("ordered_mwp"), "Balance Ordering MWp": g("balance_mwp"),
        "Total Receipt MWp": g("receipt_mwp"), "Erection done MWp": g("erection_mwp"),
        "Module Inventory MWp": g("inventory_mwp"), "Under Transit MWp": g("transit_mwp"),
        "Piles / Structure / Modules done": [pct("piles_pct"), pct("structure_pct"), pct("modules_pct")],
        "Behind plan (points)": g("behind_plan_pts"),
        "Structure ready, no modules (MWdc)": g("structure_ready_no_modules_mwdc"),
        "Module supply vs site": g("supply_vs_site"), "FTC forecast (site speed)": g("ftc_forecast_cell"),
        "Monthly plan timed by": g("plan_timed_by"), "Status": g("status"),
        "FTC Date": g("ftc_cell"), "TC Date": g("tc_cell"), "Module Date": g("module_cell"),
        "PO Placed (Actual)": g("po_placed_cell"),
        "Month wise Module Requirement at Site (MWp / MWac)": {
            m.strftime("%b-%y"): [float(a), float(b)]
            for m, a, b in zip(plan["month"], plan["plan_mwp"], plan["plan_mwac"])} if len(plan) else {},
        "planning_flags": flags,
        "ftc_max_short_days": g("rule_shortfall_days"),
        "Remarks": (g("remarks") or "")[:900],
        "_row": f"Module Deliveries.csv Sr {g('sr')} ({g('epc_group')})",
    }


# ── the review ───────────────────────────────────────────────────────────────

def _compact(result: dict) -> dict:
    """The ML result as the reviewer needs it - small enough for Groq's per-request cap."""
    out = {k: v for k, v in result.items() if k not in ("explanation", "project", "model", "monthly_requirement")}
    m = result.get("model") or {}
    out["model"] = {k: m.get(k) for k in ("site_shift_days", "transmission_shift_days", "lead_time_p50_days",
                                          "lead_time_p90_days", "supply_shortfall_days", "deadline",
                                          "deadline_basis", "contract_type") if k in m}
    mr = result.get("monthly_requirement")
    if mr:
        out["monthly_requirement"] = {
            "ai_timed_by": mr["ai"]["timed_by"],
            "ai": [[x["month"], x["required_at_site_mwp"], x["order_by_date"]] for x in mr["ai"]["months"]],
            "rule_engine": [[x["month"], x["required_at_site_mwp"], x["order_by_date"]]
                            for x in mr["rule_engine"]["months"]]}
    return out


def _date(v) -> Optional[date]:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _parse(use_case: str, data: dict) -> tuple[dict, list]:
    """Typed corrections from the LLM reply; malformed values are dropped and listed."""
    bad = []
    if use_case == "uc1":
        raw = data.get("ai_monthly_order_tc_forecast") or {}
        out = {}
        for k in UC1_FIELDS:
            if k not in raw or raw[k] in (None, ""):
                continue
            v = str(raw[k]).strip().upper() if k == "risk_level" else _date(raw[k])
            if (k == "risk_level" and v in RISKS) or (k != "risk_level" and v):
                out[k] = v
            else:
                bad.append(f"{k}={raw[k]!r} is not a valid value")
        return out, bad
    raw = data.get("ai_priority") or {}
    v = str(raw.get("priority_class", "")).strip().upper()
    if not v:
        return {}, bad
    if v in CLASSES:
        return {"priority_class": v}, bad
    return {}, [f"priority_class={raw.get('priority_class')!r} is not P1 / P2 / STANDARD"]


def review(use_case: str, request: dict, result: dict) -> Optional[Review]:
    """LLM review of one ML result. None when no LLM is configured or it fails -
    the caller then returns the ML result unchanged, marked NOT_REVIEWED."""
    pid = (result.get("project") or {}).get("p6_name") or request.get("project_id")
    row = md_row(pid, request.get("project_name"))
    facts = {
        "Today": date.today().isoformat(),
        "API request": {k: v for k, v in request.items() if v not in (None, "")},
        "ML result under review": _compact(result),
        "Module Deliveries data (planner sheet, as of 9 Oct 2026)": (
            {k: v for k, v in row.items() if k != "_row"} if row else "project not found in Module Deliveries.csv"),
    }
    got = explain._call_llm(PROMPT + SCOPE[use_case], facts)
    if not got:
        return None
    data, provider = got
    corrections, bad = _parse(use_case, data)
    status = str(data.get("ai_review_status") or "").strip().upper() or ("CORRECTED" if corrections else "VALIDATED")
    reason = str(data.get("ai_review_reason") or "").strip()
    return Review(status=status, reason=reason, corrections=corrections, provider=provider,
                  source=row["_row"] if row else None, malformed=bad)


def record(rv: Optional[Review], applied: list, rejected: list) -> dict:
    """model.llm_review: what the review proposed and what was applied."""
    if rv is None:
        return {"status": "NOT_REVIEWED", "reason": "LLM review unavailable (no provider configured, or the call "
                                                    "failed) - ML result returned unchanged.",
                "corrections": [], "rejected": []}
    rejected = list(rejected) + rv.malformed
    return {
        "status": "CORRECTED" if applied else "VALIDATED",
        "reason": rv.reason or ("Consistent with the planning data." if not applied else ""),
        "corrections": [{"field": f, "ml_value": a, "reviewed_value": b} for f, a, b in applied],
        "rejected": rejected,
        "llm_status": rv.status, "provider": rv.provider, "source": rv.source,
        "basis": "Akasha AI Governance Layer prompt over the ML result and the Module Deliveries row",
    }
