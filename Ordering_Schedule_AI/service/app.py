"""Ordering Schedule AI service.

    cd Ordering_Schedule_AI && uvicorn service.app:app --port 8000

    POST /api/ai/v1/order-tc-forecast?explain=true   UC1 order date & TC
    POST /api/ai/v1/priority-predict?explain=true    UC2 priority
    GET  /api/ai/v1/health, /api/ai/v1/model-info

Each response stacks three layers: the rule engine (the current Akasha
planning logic, as the benchmark), the ML prediction, and the explanation.
Everything returned is a model prediction, not a plan or SAP figure.
"""
from __future__ import annotations

from collections import defaultdict
from contextvars import ContextVar
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import explain
from .engine import CLASSES, ORIGIN, Engine, _d, phrase
import monthly
from features import RULE_LEAD_DAYS, TC_BUFFER_DAYS
from rules import priority_class, rule_order, rule_tc

class UTF8JSONResponse(JSONResponse):
    # Windows PowerShell 5.1 decodes JSON without a declared charset as
    # Latin-1, turning the explanation's bullets into 'â¢'.
    media_type = "application/json; charset=utf-8"


app = FastAPI(title="Akasha Ordering Schedule AI", version="1.0.0", default_response_class=UTF8JSONResponse)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
ENGINE = Engine()
PREFIX = "/api/ai/v1"
# The batch endpoints swap in an engine view over the uploaded file's
# projects; everything else uses the snapshot engine.
_ENGINE_CTX: ContextVar[Optional[Engine]] = ContextVar("engine", default=None)


def E() -> Engine:
    return _ENGINE_CTX.get() or ENGINE


class OrderTcRequest(BaseModel):
    project_id: str
    project_name: str = ""
    phase: str = ""
    vendor_type: str
    priority: str = "STANDARD"
    capacity_mwp: float = Field(..., gt=0)
    balance_ordering: float = Field(0, ge=0)
    inventory: float = Field(0, ge=0)
    receipt: float = Field(0, ge=0)
    under_transit: float = Field(0, ge=0)
    lta_date: Optional[date] = None
    scod_date: Optional[date] = None
    ftc_date: date
    # Optional: capacity is measured in MWac; send these when known.
    capacity_mwac: Optional[float] = Field(None, gt=0)
    ol: Optional[float] = Field(None, gt=0)
    # Optional business category (PPA / Merchant / Group); blank = read from the P6 name.
    category: str = ""


class PriorityRequest(BaseModel):
    project_id: str
    project_name: str = ""
    phase: str = ""
    category: str = ""
    capacity_mwp: float = Field(..., gt=0)
    balance_ordering: float = Field(0, ge=0)
    inventory: float = Field(0, ge=0)
    receipt: float = Field(0, ge=0)
    under_transit: float = Field(0, ge=0)
    lta_date: Optional[date] = None
    scod_date: Optional[date] = None
    ftc_date: date
    ftc_risk_flag: bool = False
    current_priority: str = "STANDARD"
    vendor_type: Optional[str] = None
    capacity_mwac: Optional[float] = Field(None, gt=0)
    ol: Optional[float] = Field(None, gt=0)


def iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def project_block(proj) -> Optional[dict]:
    if proj is None:
        return None
    # pid: the project's row in the Ordering Schedule snapshot, not a P6 object id.
    return {"p6_name": proj["p6_name"], "pid": int(proj["row_id"]), "project": proj["project"],
            "match_source": "Ordering Schedule snapshot"}


def _v(proj, col):
    if proj is None or col not in proj or proj[col] != proj[col]:
        return None
    v = proj[col]
    return v.date().isoformat() if hasattr(v, "date") else (round(float(v), 1) if isinstance(v, float) else v)


def project_data(proj, prow, req: dict, base) -> dict:
    """'Current Project Data' for the copilot, in the business column names.
    Request values first; the snapshot fills the rest (project level)."""
    pct = lambda c: None if _v(proj, c) is None else f"{_v(proj, c) * 100:.0f}%"  # noqa: E731
    flags = {
        "Quota moved (vendor monthly quota full)": bool(_v(proj, "rule_quota_pushed")),
        "Rule engine only - overdue ordering on P6 dates (not the AI order date)": bool(_v(proj, "rule_overdue_order")),
        "FTC after LTA": bool(_v(proj, "rule_ftc_past_lta")),
        "Vendor capacity delay beyond LTA": bool(_v(proj, "rule_capacity_delayed_past_lta")),
        "FTC at risk - planner shortfall days": _v(proj, "rule_shortfall_days"),
    } if proj is not None else None
    # The planner's free-text Remarks are left out: they still carry the old
    # planning logic (KT call, 9 Oct) and describe other phases, and the copilot
    # repeated them as advice. The structured flags above carry the signals.
    return {
        "Project": req.get("project_name") or _v(proj, "project"), "P6 Name": _v(proj, "p6_name"),
        "Category": base["contract_type"].iloc[0], "Type": req.get("vendor_type") or _v(proj, "vendor_type"),
        "Priority": req.get("priority") or req.get("current_priority"), "Phase": req.get("phase"),
        "Phase Size MWac": None if prow is None else float(prow["phase_mwac"]),
        "Capacity MWac": round(float(base["capacity_mwac"].iloc[0]), 1) if base["capacity_mwac"].iloc[0] else None,
        "Capacity MWp": req.get("capacity_mwp"), "Ordered MWp (project)": _v(proj, "ordered_mwp"),
        "Balance Ordering MWp": req.get("balance_ordering"), "Total Receipt MWp": req.get("receipt"),
        "Erection Done MWp (project)": _v(proj, "erection_mwp"), "Module Inventory MWp": req.get("inventory"),
        "Under Transit MWp": req.get("under_transit"),
        "LTA": iso(req.get("lta_date")), "SCOD": iso(req.get("scod_date")), "AOP": _v(proj, "aop"),
        "FTC Date (P6)": iso(req.get("ftc_date")),
        "Construction progress (P6)": None if proj is None else
        {"piles": pct("piles_pct"), "structure": pct("structure_pct"), "modules mounted": pct("modules_pct")},
        "Planning engine flags": flags,
    }


def status_facts(ctype: str, dl_src: str, dl, days_after: Optional[int], lta, lta_binds: bool) -> dict:
    """Plain-language status lines, so the copilot does not have to infer them
    (it once wrote 'SCOD met' for a phase 145 days past SCOD)."""
    if days_after is None:
        dl_status = "no deadline date available"
    elif days_after > 0:
        dl_status = f"MISSED - charging {days_after} days after {dl_src} ({iso(dl)})"
    else:
        dl_status = f"met - {-days_after} days of margin before {dl_src} ({iso(dl)})"
    ld = ("YES - PPA project charging after SCOD carries liquidated damages" if ctype == "PPA" and days_after
          and days_after > 0 else "none - " + ("not a PPA project" if ctype != "PPA" else "SCOD is met"))
    tx = ("binding - LTA is after the deadline, so transmission, not supply, limits export" if lta_binds
          else ("LTA came after the deadline but before realistic charging - transmission is no longer the "
                "constraint" if lta and dl and lta > dl
                else ("ready by the deadline" if lta else "no LTA date available")))
    return {"Deadline status": dl_status, "LD exposure": ld, "Transmission status": tx}


def transmission_binds(lta: Optional[date], dl: Optional[date], realistic: date) -> bool:
    """LTA after the deadline lets a phase wait - but only until the LTA. Once
    the phase realistically charges after the LTA, transmission no longer
    holds it (TPL-D: LTA 30-Jun-26 after SCOD, charging ~Dec-27)."""
    return bool(lta and dl and lta > dl and realistic <= lta)


def penalty_guardrail(cls: str, ctype: str, realistic: date, dl: Optional[date], lta: Optional[date]):
    """Hard business rule over the model: a PPA phase that will charge after
    SCOD - and after the LTA, when transmission came later than SCOD - carries
    the penalty, so it is P1. The trained model learned the rule label 'LTA
    after the deadline -> the phase can wait' without the 'until the LTA'
    part, so this also corrects it there. Returns (class, guardrail note)."""
    if ctype != "PPA" or dl is None or cls == "P1":
        return cls, None
    excused = max(dl, lta) if lta else dl
    late = (realistic - excused).days
    if late <= 0:
        return cls, None
    if lta and lta > dl:
        why = (f"PPA charging {late} days after the LTA ({iso(lta)}), which itself came after SCOD - waiting for "
               "transmission no longer explains the delay; penalty exposure is P1 by business rule")
    else:
        why = f"PPA charging {late} days after SCOD with transmission ready - penalty exposure is P1 by business rule"
    return "P1", {"applied": True, "model_class": cls, "reason": why}


def _f(x, default=0.0) -> float:
    return default if x is None or x != x else float(x)


def monthly_requirement(proj, prow, req: dict, vendor: str, ol: float, balance_mwac: float, site_shift: float,
                        lta, dl, p90: float, today: date) -> dict:
    """Month-wise Module Requirement at Site (MWp / MWac), rule engine and AI.

    Project level, like the sheet: the balance is funded across the project's
    pending phases. The requested phase uses the request's FTC; the others keep
    their P6 FTC. AI timing: the planner's 'Site speed' projects (P6 measures
    a structure pace) are paced by structure completion; the rest land in the
    TC month of the AI effective FTC (P6 FTC + site shift, or LTA if it binds).
    """
    if proj is not None:
        ph = E().phases[E().phases["row_id"] == proj["row_id"]]
        phases = [monthly.Phase(r["phase"], float(r["phase_mwac"]),
                                req["ftc_date"] if prow is not None and r["phase"] == prow["phase"]
                                else _d(r["ftc_date"])) for _, r in ph.iterrows() if _d(r["ftc_date"])]
    else:
        phases = []
    if not phases:
        cap = _f(req.get("capacity_mwac")) or req["capacity_mwp"] / ol
        phases = [monthly.Phase(req.get("phase") or "Requested phase", cap, req["ftc_date"])]

    rule = monthly.rule_plan(phases, balance_mwac, ol, vendor, today)

    pace = _f(proj["structure_pace_per_day"]) if proj is not None else 0.0
    paced = proj is not None and pace > 0 and (proj["plan_timed_by"] == "Site speed"
                                               or _f(proj["structure_done_mwdc"]) > 0)
    if paced:
        done = _f(proj["structure_done_mwdc"])
        ai = monthly.ai_site_paced_plan(
            balance_mwac, ol, pace, backlog_mwdc=done - _f(proj["modules_done_mwdc"]),
            stock_mwp=_f(req.get("inventory")) + _f(req.get("under_transit")),
            structure_left_mwdc=_f(proj["scope_mwdc"]) - done, today=today, lead_p90=p90)
        basis = (f"Site speed - P6 structure pace {pace:g} MWdc/day; inventory and in-transit stock used first, "
                 f"then modules are needed as structures are completed")
    else:
        funded = [(p, q, p.ftc + timedelta(days=round(max(site_shift, E().transmission_shift(p.ftc, lta, dl)))))
                  for p, q in monthly.fund(phases, balance_mwac, None)]
        ai = monthly.ai_phase_plan(funded, ol, p90, today)
        basis = (f"FTC date - each funded phase lands in the TC month of its AI effective FTC "
                 f"(P6 FTC + {site_shift:.0f} d site readiness, or LTA when transmission binds)")
    return {
        "unit_note": "MWp = MWac x OL (OL " + f"{ol:g}); requirement = modules needed at site in that month",
        "balance_ordering_mwp": round(balance_mwac * ol, 1), "balance_ordering_mwac": round(balance_mwac, 1),
        "rule_engine": {"basis": f"Planning Rules - phases funded from the balance in order-date sequence, each in "
                                 f"its TC month (P6 FTC - {TC_BUFFER_DAYS} d); order-by = TC - "
                                 f"{RULE_LEAD_DAYS.get(vendor)} d ({vendor})",
                        "lead_time_days": RULE_LEAD_DAYS.get(vendor),
                        "total_mwp": monthly.total_mwp(rule), "months": rule},
        "ai": {"basis": basis, "timed_by": "Site speed" if paced else "FTC date",
               "lead_time_p90_days": round(p90), "order_by_rule": "need date - measured P90 lead time (Ariba)",
               "total_mwp": monthly.total_mwp(ai), "months": ai},
        "label": "forecast - inferred from P6 dates, P6 structure pace and measured lead times, not an order plan",
    }


def order_status_lines(s: dict, pred_tc: Optional[date]) -> tuple[str, str]:
    """Fallback for the LLM's order_schedule_status_msg / short_insight (UC1),
    from the same signals the LLM reads. First matching state wins."""
    tc = pred_tc.strftime("%d-%b-%y") if pred_tc else None
    if s["Nothing left to order"]:
        return ("Nothing left to order", "Fully ordered - modules at site follow site readiness"
                + (f", ~{tc}" if tc else ""))
    if s["AI ordering window passed (order now)"]:
        return ("Ordering window passed", "Overdue - ordering window already passed, place in the earliest open month")
    if s["Vendor monthly quota moved the planner's order"]:
        return ("Moved by vendor quota", "Vendor quota full - order moved to a later month; watch the FTC")
    if s["Transmission (LTA) later than deadline - phase extended to LTA"]:
        return ("Extended to LTA", f"Extended to LTA {s['LTA date']} - transmission sets the date, safe to order later")
    order_by = date.fromisoformat(s["AI order-by date"]).strftime("%d-%b-%y")
    if s["Site readiness sets the charging date"]:
        return ("Within ordering window", f"Order by {order_by} - site readiness, not supply, sets charging")
    if s["Projected charging after the deadline"]:
        return ("Within ordering window", f"Order by {order_by} - supply in time, but charging lands after the deadline")
    return ("Within ordering window", f"On track - order by {order_by}" + (f", modules at site ~{tc}" if tc else ""))


def run_priority(req: dict, contract: Optional[str], today: date, ftc_risk_flag: bool = False, matched=None):
    proj, prow = matched or E().match(req["project_id"], req.get("project_name"), req.get("capacity_mwp"),
                                      req.get("phase"))
    base, notes = E().base_row(req, proj, prow, contract)
    X = E()._features(base, today)
    if ftc_risk_flag:
        X.loc[:, "ftc_risk_flag"] = 1.0
    site_shift, site_drivers = E().site_shift(X)
    cls, probs, drivers = E().priority(E().stacked(X, site_shift))
    return proj, prow, base, X, cls, probs, drivers, notes, site_shift, site_drivers


# ── UC1 ──────────────────────────────────────────────────────────────────────

@app.post(f"{PREFIX}/order-tc-forecast")
def order_tc_forecast(body: OrderTcRequest, explain_: bool = Query(False, alias="explain")):
    return uc1(body, explain_)


def uc1(body: OrderTcRequest, explain_: bool, matched=None, order_mwp: Optional[float] = None,
        use_llm: bool = True) -> dict:
    """UC1. matched: (project, phase) rows when the caller already knows them
    (batch). order_mwp: this phase's own share of the balance (Planning Rules
    funding); body.balance_ordering stays the project balance, as in training
    and in the monthly plan."""
    req = body.model_dump()
    req["vendor_type"] = next((k for k in RULE_LEAD_DAYS if k.lower() == body.vendor_type.lower()), body.vendor_type)
    vendor = req["vendor_type"]
    today = date.today()
    contract = body.category.strip().upper() or None
    if contract and contract not in ("PPA", "MERCHANT", "GROUP"):
        raise HTTPException(422, "category must be PPA, Merchant or Group")
    proj, prow, base, X, ai_cls, probs, _, notes, site_shift, site_drivers = run_priority(req, contract, today,
                                                                                          matched=matched)
    ftc, lta = body.ftc_date, body.lta_date
    dl, dl_src = E().deadline_of(base)

    # Same priority guardrail as /priority-predict, on this phase's realistic FTC.
    real_ftc = ftc + timedelta(days=round(max(site_shift, E().supply_shortfall(
        ftc, vendor, body.balance_ordering, today))))
    ai_cls, prio_guard = penalty_guardrail(ai_cls, base["contract_type"].iloc[0], real_ftc, dl, lta)

    # Rule engine (benchmark)
    r_tc, r_order = rule_tc(ftc), rule_order(ftc, vendor)

    # ML: how far site readiness pushes FTC (site_shift, above); planner rule:
    # LTA after deadline -> wait for it
    trans_shift = E().transmission_shift(ftc, lta, dl)
    target_ftc = ftc + timedelta(days=round(max(site_shift, trans_shift)))
    need_tc = target_ftc - timedelta(days=TC_BUFFER_DAYS)

    # ML: measured supply lead time for this order size (Ariba, LightGBM quantile)
    phase_order = order_mwp
    to_order = (phase_order if phase_order is not None else body.balance_ordering) > 0
    order_mwp = (phase_order if phase_order else body.balance_ordering) or body.capacity_mwp
    p50, p90 = E().lead_times(vendor, order_mwp, notes)
    if p50 is None:
        raise HTTPException(422, f"vendor_type '{body.vendor_type}' has no lead-time data; use one of "
                                 f"{sorted(RULE_LEAD_DAYS)}")
    ol = body.capacity_mwp / float(base["capacity_mwac"].iloc[0])
    month_plan = monthly_requirement(proj, prow, req, vendor, ol, float(base["balance_mwac"].iloc[0]),
                                     site_shift, lta, dl, p90, today)
    ai_months = month_plan["ai"]["months"]
    if month_plan["ai"]["timed_by"] == "Site speed" and ai_months:
        # Structures set the need date: the first month stock runs short.
        need_tc = date.fromisoformat(ai_months[0]["need_date"])
    if to_order:
        order_by = need_tc - timedelta(days=round(p90))      # even a P90 delivery meets the need date
        order_now = order_by <= today
        recommended = max(order_by, today)
        pred_tc = recommended + timedelta(days=round(p50))
        pred_tc_p90 = recommended + timedelta(days=round(p90))
    else:
        order_by = recommended = None
        order_now = False
        pred_tc, pred_tc_p90 = need_tc, None
    projected_ftc = max(target_ftc, pred_tc + timedelta(days=TC_BUFFER_DAYS))
    breach = (projected_ftc - dl).days if dl else None

    # Root cause: parts partition the total shift (no double counting).
    total = (projected_ftc - ftc).days
    transmission_days = min(trans_shift, total)
    progress_days = max(0, round(site_shift) - trans_shift)
    material_days = (projected_ftc - target_ftc).days
    breakdown = [
        {"reason": "Progress delay (site readiness, ML)", "days": progress_days},
        {"reason": "Material delay (ordering vs measured lead time)", "days": material_days},
        {"reason": "Transmission delay (LTA after deadline)", "days": transmission_days},
        {"reason": "Weather impact", "days": None, "note": "no weather data in the sources yet"},
    ]
    named = [b for b in breakdown if b["days"]]
    main = " and ".join(b["reason"].split(" (")[0].lower() for b in sorted(named, key=lambda b: -b["days"])[:2])
    root_cause = {
        "predicted_ftc_shift_days": total,
        "breakdown": breakdown,
        "summary": (f"FTC shifted by {total} days, mainly due to {main}." if total > 0 and main
                    else "No FTC shift predicted beyond the P6 date."),
    }

    if (breach is not None and breach > 0) or (to_order and order_by and order_by < today):
        risk = "HIGH"
    elif breach is not None and breach > -60:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    coverage = float(X.iloc[0].notna().mean())
    confidence = round(coverage * E().site_skill, 2)

    shift_vs_rule = (order_by - r_order).days if (order_by and r_order) else None
    key_drivers = []
    if to_order and phase_order is not None:
        key_drivers.append(f"{phase_order:g} MWp of this phase is still to order "
                           f"({body.balance_ordering:g} MWp across the project).")
    elif to_order:
        key_drivers.append(f"{body.balance_ordering:g} MWp of {body.capacity_mwp:g} MWp is still unordered.")
    elif phase_order is not None and body.balance_ordering > 0:
        key_drivers.append("The project balance is used up by earlier phases; under the Planning "
                           "Rules this phase counts as covered by orders already placed.")
    else:
        key_drivers.append("Nothing left to order; TC follows the effective FTC.")
    key_drivers.append(f"Inventory {body.inventory:g} MWp, received {body.receipt:g} MWp, "
                       f"in transit {body.under_transit:g} MWp.")
    key_drivers.append(f"Measured supplier lead time {p50:.0f} days (P90 {p90:.0f}) for {vendor} supply "
                       f"vs {RULE_LEAD_DAYS.get(vendor)} days in the rule engine.")
    if site_shift >= 1:
        why = "; ".join(phrase(f, v) for f, c, v in site_drivers if c > 0)
        key_drivers.append(f"Site readiness predicted to push FTC {site_shift:.0f} days past P6"
                           + (f" ({why})." if why else "."))
    if trans_shift:
        key_drivers.append(f"LTA {iso(lta)} is after the {dl_src} - the phase can wait for transmission.")
    if month_plan["ai"]["months"]:
        key_drivers.append("Modules needed at site: " + ", ".join(
            f"{m['month']} {m['required_at_site_mwp']:g} MWp" for m in month_plan["ai"]["months"][:4])
            + (" ..." if len(month_plan["ai"]["months"]) > 4 else "")
            + f" ({month_plan['ai']['timed_by'].lower()} timing).")

    risks = {
        "ftc_risk": (f"Projected charging {iso(projected_ftc)} is after the {dl_src} ({iso(dl)})."
                     if breach and breach > 0 else None),
        "vendor_capacity_risk": ("Order window already passed - order immediately." if to_order and order_now else None),
        "transmission_risk": (f"LTA {iso(lta)} after the {dl_src}: transmission, not supply, binds." if trans_shift
                              else ("FTC lands after LTA - transmission access unused until charging."
                                    if lta and projected_ftc > lta else None)),
    }
    impact = {
        "scod_impact": (f"Projected charging lands {breach} days after the {dl_src}." if breach and breach > 0
                        else (f"{-breach} days of margin to the {dl_src}." if breach is not None else None)),
        "lta_impact": risks["transmission_risk"],
        "ld_impact": ("Liquidated damages exposure is likely unless the order is expedited."
                      if breach and breach > 0 and base["contract_type"].iloc[0] == "PPA" else None),
    }
    actions = []
    if to_order:
        actions.append("Place the order now and secure the vendor slot." if order_now
                       else f"Place the order by {iso(order_by)} and secure the vendor slot.")
    actions.append("Track shipment milestones weekly against the predicted delivery date.")
    # The fix depends on which constraint binds (largest root-cause part).
    binding = max(breakdown[:3], key=lambda b: b["days"] or 0)
    if risk == "HIGH":
        if binding["days"] and binding is breakdown[0]:
            actions.append("Escalate to the project head: speed up structure work (steel supply, crews) - "
                           "site readiness, not supply, sets the charging date.")
        elif binding["days"] and binding is breakdown[2]:
            actions.append("Escalate the transmission (LTA) date; ordering earlier would only add yard stock.")
        else:
            actions.append("Escalate to the project head: consider expediting or part-shipments to protect the deadline.")
    if site_shift >= 30:
        actions.append("Pace deliveries to structure readiness - earlier delivery only adds yard stock.")

    response = {
        "recommended_order_date": iso(recommended), "predicted_tc_date": iso(pred_tc),
        "confidence": confidence, "risk_level": risk, "order_by_date": iso(order_by), "order_now": order_now,
        "predicted_tc_date_p90": iso(pred_tc_p90), "projected_ftc_date": iso(projected_ftc),
        "deadline_breach_days": breach,
        "rule_engine": {"order_by_date": iso(r_order), "tc_date": iso(r_tc)},
        "order_by_shift_vs_rule_days": shift_vs_rule,
        "priority": {"current": body.priority, "ai": ai_cls, "criticality_score": E().criticality(probs),
                     "guardrail": prio_guard},
        "project": project_block(proj),
        "root_cause": root_cause,
        "monthly_requirement": month_plan,
        "lead_time": {
            "rule_engine_days": RULE_LEAD_DAYS.get(vendor),
            "rule_engine_basis": "Planning Rules sheet: China / SEA 136 d, ALMM / ALCM / DCR 98 d (order to modules at site)",
            "ai_p50_days": round(p50), "ai_p90_days": round(p90),
            "ai_basis": f"measured on Ariba POs (order to GRN), {vendor} origin, order size "
                        f"{min(order_mwp, E().meta['uc1_lead_time'].get('max_order_mwp', {}).get(ORIGIN.get(vendor), order_mwp)):g} MWp; "
                        "P50 = typical, P90 = 9 in 10 deliveries arrive by then",
            "how_used": "AI order-by = need TC - P90; predicted TC = order date + P50 (P90 = latest likely)"},
        "model": {"site_shift_days": round(site_shift, 1), "transmission_shift_days": trans_shift,
                  "lead_time_p50_days": round(p50, 1), "lead_time_p90_days": round(p90, 1),
                  "deadline": iso(dl), "deadline_basis": dl_src, "feature_coverage": round(coverage, 2),
                  "confidence_basis": "feature coverage x share of the rule engine's FTC error the site model "
                                      "removes in grouped cross-validation",
                  "label_provenance": "site shift: inferred (sheet's site-pace forecast); lead time: measured (Ariba)",
                  "assumptions": notes, "as_of": iso(today)},
    }
    if explain_:
        template = {
            "executive_summary": (
                (f"AI recommends placing the order {'now' if order_now else 'by ' + iso(order_by)}; " if to_order
                 else "Nothing left to order; ")
                + f"modules are expected at site around {iso(pred_tc)}"
                + (f" (latest {iso(pred_tc_p90)})" if pred_tc_p90 else "")
                + f", giving first charging around {iso(projected_ftc)}. Risk level: {risk}."),
            "rule_vs_ai_assessment": (
                f"Rule Engine ordering date {iso(r_order)} and AI date {iso(order_by)} "
                + ("are close - current planning assumptions remain aligned with project conditions."
                   if shift_vs_rule is not None and abs(shift_vs_rule) <= 14 else
                   f"differ by {abs(shift_vs_rule)} days - the AI " + ("orders earlier" if shift_vs_rule < 0
                                                                        else "can order later")
                   + " because it uses measured lead times and the realistic FTC." if shift_vs_rule is not None
                   else "cannot be compared (nothing left to order).")),
            "key_drivers": key_drivers, "risks_identified": risks, "business_impact": impact,
            "recommended_actions": actions,
        }
        signals = {
            "Today": iso(today),
            "Nothing left to order": not to_order,
            "AI ordering window passed (order now)": order_now,
            "AI order-by date": iso(order_by),
            "Rule engine ordering window passed": bool(r_order and r_order < today),
            "Vendor monthly quota moved the planner's order": bool(_v(proj, "rule_quota_pushed")),
            "Transmission (LTA) later than deadline - phase extended to LTA": trans_shift > 0,
            "LTA date": iso(lta),
            "Site readiness sets the charging date": bool(binding["days"] and binding is breakdown[0]),
            "Projected charging after the deadline": bool(breach and breach > 0),
        }
        template["order_schedule_status_msg"], template["short_insight"] = order_status_lines(signals, pred_tc)
        facts = {
            "Current Project Data": project_data(proj, prow, req, base),
            "Rule Engine Outputs": {
                "Rule Ordering Date (Module Date)": iso(r_order), "Rule TC Date": iso(r_tc),
                "Rule assumes FTC = P6 FTC": iso(ftc), "Rule lead time days": RULE_LEAD_DAYS.get(vendor)},
            "AI Outputs": {
                "Predicted Ordering Date": iso(recommended) if to_order else "nothing left to order",
                "AI_order_now": order_now,
                "Predicted TC Date (modules at site)": iso(pred_tc),
                "Predicted TC Date P90 (latest likely)": iso(pred_tc_p90),
                "Projected FTC Date (first time charging)": iso(projected_ftc),
                "Confidence Score (0-1)": confidence, "Risk Level": risk,
                "AI ordering date minus rule ordering date (days)": shift_vs_rule,
                "Measured supplier lead time days (typical / P90)": [round(p50), round(p90)],
                "Days projected FTC after deadline (negative = margin)": breach,
                "Deadline used": f"{dl_src} {iso(dl)}" if dl else None,
                "FTC shift root cause (days)": {b["reason"]: b["days"] for b in breakdown if b["days"] is not None},
                "Binding constraint": binding["reason"] if binding["days"] else "none",
                "AI priority": ai_cls},
            "Status": status_facts(base["contract_type"].iloc[0], dl_src, dl, breach, lta, trans_shift > 0),
            "Month-wise Module Requirement at Site": {
                "AI timing basis": month_plan["ai"]["timed_by"],
                "AI (month: MWp / MWac, order by)": {m["month"]: [m["required_at_site_mwp"], m["required_at_site_mwac"],
                                                                 m["order_by_date"]]
                                                     for m in month_plan["ai"]["months"]},
                "Rule Engine (month: MWp / MWac)": {m["month"]: [m["required_at_site_mwp"], m["required_at_site_mwac"]]
                                                    for m in month_plan["rule_engine"]["months"]}},
            "Computed drivers": key_drivers,
            "Computed actions (consistent with the AI result)": actions,
            "Ordering schedule signals": signals,
        }
        response["explanation"] = explain.build(template, facts, "uc1", use_llm=use_llm)
    return response


# ── UC2 ──────────────────────────────────────────────────────────────────────

@app.post(f"{PREFIX}/priority-predict")
def priority_predict(body: PriorityRequest, explain_: bool = Query(False, alias="explain")):
    return uc2(body, explain_)


def uc2(body: PriorityRequest, explain_: bool, matched=None, use_llm: bool = True) -> dict:
    req = body.model_dump()
    contract = body.category.strip().upper() or None
    if contract and contract not in ("PPA", "MERCHANT", "GROUP"):
        raise HTTPException(422, "category must be PPA, Merchant or Group")
    today = date.today()
    proj, prow, base, X, cls, probs, drivers, notes, site_shift, _ = run_priority(
        req, contract, today, body.ftc_risk_flag, matched=matched)
    if not req.get("vendor_type") and proj is not None:
        req["vendor_type"] = proj["vendor_type"]
    vendor = req.get("vendor_type")
    ctype = base["contract_type"].iloc[0]
    dl, dl_src = E().deadline_of(base)
    ftc = body.ftc_date

    rule_cls = priority_class(ctype, X["deadline_gap_vs_phase_ftc"].iloc[0], X["lta_after_deadline_days"].iloc[0])
    supply = E().supply_shortfall(ftc, vendor, body.balance_ordering, today)
    realistic = ftc + timedelta(days=round(max(site_shift, supply)))
    slack = (dl - realistic).days if dl else None
    cls, guard = penalty_guardrail(cls, ctype, realistic, dl, body.lta_date)
    tx_binds = transmission_binds(body.lta_date, dl, realistic)

    # Business reasons first (what the priority rests on), then the model's
    # other strongest drivers; at most 5, one line per signal.
    lead = []
    if slack is not None:
        lead.append(("realistic_slack_pred", float(slack)))
    lead.append(("category_rank", float(X["category_rank"].iloc[0]) if X["category_rank"].iloc[0] == X["category_rank"].iloc[0]
                 else None))
    if body.balance_ordering > 0:
        lead.append(("balance_share", float(X["balance_share"].iloc[0])))
    if body.balance_ordering > body.inventory + body.under_transit:
        lead.append(("inventory_share", float(X["inventory_share"].iloc[0])))
    if tx_binds:
        lead.append(("lta_after_deadline_days", float(X["lta_after_deadline_days"].iloc[0])))
    seen = {f for f, _ in lead}
    extra = [(f, v) for f, c, v in drivers if f not in seen and f not in ("deadline_gap_vs_phase_ftc", "ftc_risk_flag")
             and not (f in ("transmission_binding_flag", "lta_after_deadline_days") and (v <= 0 or not tx_binds))]
    reasons = list(dict.fromkeys(phrase(f, v) for f, v in (lead + extra) if v is not None))[:5]
    score = E().criticality(probs)
    risks = {
        "ftc_risk": (f"Realistic charging {iso(realistic)} is after the {dl_src} ({iso(dl)})."
                     if slack is not None and slack < 0 else None),
        "vendor_capacity_risk": ("Stock and in-transit material do not cover the remaining scope."
                                 if body.balance_ordering > body.inventory + body.under_transit else None),
        "transmission_risk": (f"LTA {iso(body.lta_date)} after the {dl_src}: the phase can wait for transmission."
                              if tx_binds else
                              (f"LTA {iso(body.lta_date)} came after the {dl_src}, but realistic charging is later "
                               "still - transmission no longer holds this phase."
                               if X["lta_after_deadline_days"].iloc[0] > 0 else None)),
    }
    response = {
        "priority_class": cls, "priority_score": score, "reasons": reasons,
        "rule_engine": {"priority_class": rule_cls, "basis": f"P6 FTC vs {dl_src} deadline"},
        "class_probabilities": probs, "ftc_date_used": iso(ftc), "realistic_ftc_date": iso(realistic),
        "guardrail": guard,
        "project": project_block(proj),
        "model": {"site_shift_days": round(site_shift, 1), "supply_shortfall_days": supply, "deadline": iso(dl),
                  "deadline_basis": dl_src, "contract_type": ctype,
                  "score_basis": "100 x (P(P1) + 0.5 x P(P2))",
                  "label_provenance": "weak - business rule on realistic FTC, LTA, SCOD/AOP and category; "
                                      "no planner-recorded priority exists yet",
                  "assumptions": notes, "as_of": iso(today)},
    }
    if explain_:
        same = cls == rule_cls
        template = {
            "executive_summary": (f"AI assessment: {cls} (score {score:.0f}/100). "
                                  + ("This matches the current priority." if cls == body.current_priority.upper()
                                     else f"This differs from the current priority ({body.current_priority}).")
                                  + (" The project needs procurement attention ahead of lower-priority work."
                                     if cls == "P1" else "")),
            "rule_vs_ai_assessment": (f"Rule-based priority from the planned P6 dates: {rule_cls}. AI priority, which "
                                      f"uses the realistic charging date ({iso(realistic)}): {cls}. "
                                      + ("They agree." if same else
                                         "They differ because the realistic date is later than the P6 date."
                                         if realistic > ftc else "They differ.")
                                      + (f" The model alone said {guard['model_class']}; the PPA penalty rule "
                                         f"sets P1." if guard else "")),
            "key_drivers": reasons, "risks_identified": risks,
            "business_impact": {
                "scod_impact": (f"Realistic charging is {-slack} days after the {dl_src}." if slack is not None
                                and slack < 0 else (f"{slack} days of margin to the {dl_src}." if slack is not None
                                                    else None)),
                "lta_impact": risks["transmission_risk"],
                "ld_impact": ("Liquidated damages exposure if the delay is not recovered."
                              if slack is not None and slack < 0 and ctype == "PPA" else None),
            },
            "recommended_actions": ((["Escalate construction pace (structures, steel supply, crews) - site readiness "
                                      "sets the charging date.",
                                      "Secure the vendor slot now and time deliveries to structure readiness.",
                                      "Review the LD exposure and recovery plan weekly with the project head."]
                                     if site_shift >= max(supply, 1) else
                                     ["Raise procurement attention and secure vendor allocation first.",
                                      "Review ordering progress weekly until the balance is ordered."]) if cls == "P1"
                                    else ["Keep in the standard ordering cycle; re-check after the next P6 update."]
                                    if cls == "STANDARD" else
                                    ["Order within the planned window; monitor the deadline margin monthly."]),
        }
        facts = {
            "Current Project Data": project_data(proj, prow, req, base),
            "Rule Engine Priority (planned P6 dates)": rule_cls,
            "final_priority": cls,
            "ML Predicted Priority (before business rule)": guard["model_class"] if guard else cls,
            "Business rule override": guard["reason"] if guard else None,
            "Who set the final priority": ("business rule (PPA penalty) over the AI model's "
                                           f"{guard['model_class']}" if guard else "the AI model"),
            "Status": status_facts(ctype, dl_src, dl, -slack if slack is not None else None, body.lta_date, tx_binds),
            "Priority Score (0-100)": score,
            "Confidence (0-1)": max(probs.values()),
            "Current priority": body.current_priority,
            "Realistic FTC Date (first time charging)": iso(realistic),
            "Deadline used": f"{dl_src} {iso(dl)}" if dl else None,
            "Days realistic FTC after deadline (negative = margin)": -slack if slack is not None else None,
            "Site readiness delay days": round(site_shift),
            "Supply delay if ordered today days": supply,
            "Binding constraint": ("site readiness - structures are not ready, so ordering or shipping earlier only "
                                   "adds yard stock; the fix is construction pace" if site_shift >= supply and
                                   site_shift >= 1 else ("supply - the order is late for the lead time"
                                                         if supply > 0 else "none")),
            "Transmission binds (LTA after deadline and after realistic charging)": tx_binds,
            "Computed drivers": reasons,
        }
        response["explanation"] = explain.build(template, facts, "uc2", use_llm=use_llm)
    return response


# ── UC1 portfolio: month-wise requirement by contractor ─────────────────────

def _snapshot_request(proj) -> Optional[OrderTcRequest]:
    """A UC1 request for a snapshot project: its earliest pending phase and P6 FTC."""
    ph = E().phases[E().phases["row_id"] == proj["row_id"]].sort_values("ftc_date")
    ph = ph[ph["ftc_date"].notna()]
    if ph.empty or not proj["vendor_type"] in RULE_LEAD_DAYS:
        return None
    first = ph.iloc[0]
    return OrderTcRequest(
        project_id=proj["p6_name"], project_name=proj["project"], phase=first["phase"],
        vendor_type=proj["vendor_type"], priority=proj["priority"] if isinstance(proj["priority"], str) else "STANDARD",
        capacity_mwp=float(proj["capacity_mwac"]) * float(proj["ol"]),
        capacity_mwac=float(proj["capacity_mwac"]), ol=float(proj["ol"]),
        balance_ordering=_f(proj["balance_mwp"]), inventory=_f(proj["inventory_mwp"]),
        receipt=_f(proj["receipt_mwp"]), under_transit=_f(proj["transit_mwp"]),
        lta_date=_d(proj["lta"]), scod_date=_d(proj["scod"]), ftc_date=_d(first["ftc_date"]))


@app.get(f"{PREFIX}/monthly-plan")
def monthly_plan(epc: Optional[str] = Query(None, description="Contractor (EPC) name, e.g. 'Amara Raja'; "
                                                               "omit for every contractor")):
    """Month-wise Module Requirement at Site (MWp / MWac) per contractor, rule
    engine vs AI, grouped like the Module Deliveries sheet. The group's MWp is
    the SUM of its projects' capacities (MWac x OL), not a figure divided
    among them."""
    projs = E().projects
    if epc:
        projs = projs[projs["epc_group"].fillna("").str.lower().str.contains(epc.strip().lower(), regex=False)]
        if projs.empty:
            raise HTTPException(404, f"no contractor matching '{epc}'; known: "
                                     f"{sorted(E().projects['epc_group'].dropna().unique())}")
    groups, quota = [], defaultdict(float)
    for name, g in projs.groupby("epc_group", sort=False):
        rows, totals = [], {"rule_engine": defaultdict(lambda: [0.0, 0.0]), "ai": defaultdict(lambda: [0.0, 0.0])}
        for _, p in g.iterrows():
            cap_mwp = round(float(p["capacity_mwac"]) * float(p["ol"]), 2)
            item = {"project": p["project"], "p6_name": p["p6_name"], "vendor_type": p["vendor_type"],
                    "capacity_mwac": float(p["capacity_mwac"]), "ol": float(p["ol"]), "capacity_mwp": cap_mwp,
                    "balance_ordering_mwp": _f(p["balance_mwp"])}
            req = _snapshot_request(p) if _f(p["balance_mwp"]) > 0 and not bool(p["all_phases_charged"]) else None
            if req is None:
                item["status"] = ("nothing left to order" if _f(p["balance_mwp"]) <= 0
                                  else "no pending phase with an FTC / no lead-time data - not planned")
            else:
                r = order_tc_forecast(req, False)
                mp = r["monthly_requirement"]
                item.update(order_by_date=r["order_by_date"], predicted_tc_date=r["predicted_tc_date"],
                            projected_ftc_date=r["projected_ftc_date"], risk_level=r["risk_level"],
                            rule_order_by_date=r["rule_engine"]["order_by_date"], rule_tc_date=r["rule_engine"]["tc_date"],
                            monthly_requirement={"ai_timed_by": mp["ai"]["timed_by"],
                                                 "ai": mp["ai"]["months"], "rule_engine": mp["rule_engine"]["months"]})
                for k in ("ai", "rule_engine"):
                    for m in mp[k]["months"]:
                        t = totals[k][m["month"]]
                        t[0] += m["required_at_site_mwp"]
                        t[1] += m["required_at_site_mwac"]
                for m in mp["ai"]["months"]:
                    if m["order_month"]:
                        quota[(p["vendor_type"], m["order_month"])] += m["required_at_site_mwac"]
            rows.append(item)
        cap = round(sum(r["capacity_mwp"] for r in rows), 2)

        def month_list(d):
            keys = sorted(d, key=lambda k: date(2000 + int(k[-2:]), datetime.strptime(k[:3], "%b").month, 1))
            return [{"month": k, "required_at_site_mwp": round(d[k][0], 1), "required_at_site_mwac": round(d[k][1], 1)}
                    for k in keys]
        groups.append({"epc": name, "header": f"{name} ({len(rows)} projects · {cap:g} MWp)",
                       "capacity_mwp_total": cap,
                       "capacity_note": "sum of each project's capacity (MWac x OL); each project keeps its own size",
                       "monthly_total": {"ai": month_list(totals["ai"]), "rule_engine": month_list(totals["rule_engine"])},
                       "projects": rows})
    checks = [{"vendor_type": v, "order_month": m, "ai_orders_mwac": round(q, 1),
               "ceiling_mwac": monthly.VENDOR_QUOTA_MWAC.get(v),
               "over_ceiling": bool(monthly.VENDOR_QUOTA_MWAC.get(v) and q > monthly.VENDOR_QUOTA_MWAC[v])}
              for (v, m), q in sorted(quota.items())]
    return {"as_of": iso(date.today()), "groups": groups,
            "vendor_quota_check": {"basis": "AI orders placed per month vs the Planning Rules monthly ceilings "
                                            "(MWac); flagged, not levelled" + ("" if not epc else
                                            " - this contractor's orders only, other contractors share the quota"),
                                   "months": checks},
            "label": "forecast - inferred from P6 dates, P6 structure pace and measured lead times, not an order plan"}


@app.get(f"{PREFIX}/health")
def health():
    return {"status": "ok", "models_trained_at": E().meta["trained_at"], "data_as_of": E().meta["data_as_of"]}


@app.get(f"{PREFIX}/model-info")
def model_info():
    m = E().meta
    return {k: m[k] for k in ("trained_at", "data_as_of", "features", "uc1_site_shift", "uc1_lead_time",
                              "uc2_priority", "label_provenance", "mlflow_runs")}


# Batch: a whole Module Deliveries file in, the same file with AI columns out.
from .batch import router as batch_router  # noqa: E402

app.include_router(batch_router)
from .dashboard import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)
