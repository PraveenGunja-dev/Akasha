"""Batch scoring of a Module Deliveries file: UC1 + UC2 for every project.

    POST /api/ai/v1/batch/module-deliveries/csv    multipart file  -> CSV
    POST /api/ai/v1/batch/module-deliveries/json   JSON body       -> JSON

Input is the Module Deliveries sheet (data/raw/Module Deliveries.csv): the CSV
endpoint takes the export as-is (title rows, two-row header, EPC group rows);
the JSON endpoint takes one object per project row keyed by the same column
headers. Output is the input with AI columns appended to each project row, so
the dashboard shows the sheet and the AI side by side.

Each pending FTC phase is scored with the same code as the single-project
endpoints. Site Productivity (P6 pace, planned %, data date) is not in this
sheet: it is joined from the training snapshot by P6 name, and a project the
snapshot does not know is scored without it (said in AI Status).
"""
from __future__ import annotations

import contextvars
import copy
import csv
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any, Literal, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from fastapi.responses import Response

import parsers as P
from build_datasets import build_phase_frame, project_table
from features import RULE_LEAD_DAYS

from . import app as core

router = APIRouter(prefix=f"{core.PREFIX}/batch/module-deliveries", tags=["batch"])
RANK = {"P1": 2, "P2": 1, "STANDARD": 0}
SP_COLS = ["mms_type_sp", "p6_data_date", "p6_final_ftc", "scope_mwdc"] + [
    f"{k}_{c}" for k in ("piles", "structure", "modules")
    for c in ("done_mwdc", "planned_pct", "pace_per_day", "needed_per_day", "manpower_needed")] + ["modules_finish_at_pace"]
MONTH_RE = re.compile(r"[A-Z][a-z]{2}-\d{2}")

# Appended columns, in order. Phase-level values are one line per phase
# ('Ph-I: 27-Jan-27'), as in the sheet's FTC / TC / Module Date cells.
AI_COLUMNS = [
    "AI Status", "AI Priority", "AI Priority Set By", "AI Priority Score (model)", "Rule Priority (P6 dates)",
    "AI Priority Reasons",
    "AI Module Order Date", "AI Order Now", "AI TC Date", "AI TC Date (P90)", "AI FTC (projected)",
    "AI Risk Level", "AI Days After Deadline", "AI Lead Time (P50 / P90 days)",
    "AI Month wise Module Requirement at Site (MWp / MWac)", "AI Root Cause", "AI Confidence",
    "AI Explanation - Order & TC (UC1)", "AI Explanation - Priority (UC2)", "AI As Of",
]


# ── input ────────────────────────────────────────────────────────────────────

def rows_from_csv(data: bytes) -> list[list[str]]:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return list(csv.reader(io.StringIO(data.decode(enc), newline="")))
        except UnicodeDecodeError:
            continue
    raise HTTPException(422, "CSV is neither UTF-8 nor Windows-1252 text")


def _norm(k: str) -> str:
    return re.sub(r"\s+", " ", str(k)).strip()


def rows_from_records(records: list[dict]) -> list[list[str]]:
    """JSON records -> the sheet's row layout, so one parser reads both."""
    if not records or not all(isinstance(r, dict) for r in records):
        raise HTTPException(422, "JSON must be a list of project objects, or {\"rows\": [...]}")
    keys: list[str] = []
    for r in records:
        for k in r:
            if k not in keys:
                keys.append(k)
    group_key = next((k for k in keys if _norm(k).lower() in ("epc group", "epc_group")), None)
    sr_key = next((k for k in keys if _norm(k) == "Sr"), None)
    cols = [k for k in keys if k not in (group_key, sr_key)]
    header = ["Sr"] + [("" if MONTH_RE.fullmatch(_norm(k)) else _norm(k)) for k in cols]
    sub = [""] + [(_norm(k) if MONTH_RE.fullmatch(_norm(k)) else "") for k in cols]
    rows, group = [header, sub], None
    for i, r in enumerate(records, start=1):
        g = r.get(group_key) if group_key else None
        if g and g != group:
            rows.append([f"{g}   (group)"] + [""] * len(cols))
            group = g
        sr = str(r.get(sr_key, "")).strip() if sr_key else ""
        rows.append([sr if sr.isdigit() else str(i)] + ["" if r.get(k) is None else str(r.get(k)) for k in cols])
    return rows


# ── scoring ──────────────────────────────────────────────────────────────────

def _dmy(s: Optional[str]) -> str:
    return date.fromisoformat(s).strftime("%d-%b-%y") if s else "-"


def _num(x) -> Optional[float]:
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def _snapshot_site(md: pd.DataFrame) -> pd.DataFrame:
    snap = core.ENGINE.projects.assign(_k=core.ENGINE.projects["p6_name"].fillna("").str.strip())
    snap = snap.drop_duplicates("_k").set_index("_k")[SP_COLS]
    sp = md[["row_id", "project"]].assign(_k=md["p6_name"].fillna("").str.strip())
    sp = sp.join(snap, on="_k").drop(columns="_k")
    return sp.rename(columns={"row_id": "sp_block", "project": "sp_project"})


def score(rows: list[list[str]], as_of_override: Optional[date], explain: str) -> tuple[pd.DataFrame, dict]:
    """Every project row -> {AI column: value} plus a structured detail."""
    try:
        md, plan = P.parse_module_deliveries_rows(rows)
    except ValueError as e:
        raise HTTPException(422, f"not a Module Deliveries layout: {e}")
    as_of = pd.Timestamp(as_of_override or P.as_of_from_rows(rows) or date.today())
    sp = _snapshot_site(md)
    in_snapshot = dict(zip(sp["sp_block"], sp["scope_mwdc"].notna() | sp["p6_data_date"].notna()))
    projects = project_table(md, sp, plan, as_of)
    phases = P.explode_phases(md)
    pf = build_phase_frame(phases, projects, as_of) if not phases.empty else pd.DataFrame(columns=["row_id"])

    view = copy.copy(core.ENGINE)
    view.projects, view.phases = projects, pf
    token = core._ENGINE_CTX.set(view)
    try:
        jobs, out = [], {}
        for _, proj in projects.iterrows():
            out[proj["row_id"]] = _score_project(proj, pf, bool(in_snapshot[proj["row_id"]]), as_of, jobs)
        if explain == "llm" and jobs:
            # One LLM call per use case for each project's lead phase; the rest keep the template.
            with ThreadPoolExecutor(max_workers=3) as pool:   # provider rate limits
                futs = [(rid, k, pool.submit(contextvars.copy_context().run, fn)) for rid, k, fn in jobs]
                for rid, k, f in futs:
                    try:
                        out[rid]["cols"][k] = f.result()["explanation"]["text"]
                    except Exception:  # noqa: BLE001 - the template text already stands
                        pass
    finally:
        core._ENGINE_CTX.reset(token)
    if explain == "none":
        for v in out.values():
            v["cols"]["AI Explanation - Order & TC (UC1)"] = v["cols"]["AI Explanation - Priority (UC2)"] = ""
            for ph in v["detail"].get("phases", []):
                ph.pop("explanation_uc1", None), ph.pop("explanation_uc2", None)
    return md, out


def _score_project(proj, pf: pd.DataFrame, in_snapshot: bool, as_of, jobs: list) -> dict:
    cols = {c: "" for c in AI_COLUMNS}
    cols["AI As Of"] = date.today().strftime("%d-%b-%y")
    ph = pf[pf["row_id"] == proj["row_id"]].sort_values(["ftc_date", "phase_idx"]) if len(pf) else pf
    vendor = proj["vendor_type"] if proj["vendor_type"] in RULE_LEAD_DAYS else None
    ol, cap = _num(proj["ol"]), _num(proj["capacity_mwac"])
    detail: dict[str, Any] = {"phases": []}

    if bool(proj["all_phases_charged"]):
        cols["AI Status"] = "Not scored - no pending FTC phase (all phases charged)"
        return {"cols": cols, "detail": detail}
    if ph.empty or not cap:
        cols["AI Status"] = "Not scored - " + ("no capacity" if not cap else "no FTC date in the FTC Date cell")
        return {"cols": cols, "detail": detail}

    cap_mwp = cap * ol if ol else (_num(proj["capacity_mwp"]) or cap * core.ENGINE.median_ol)
    q = lambda c: _num(proj[c]) or 0.0  # noqa: E731
    common = dict(project_id=proj["p6_name"] or proj["project"], project_name=proj["project"],
                  capacity_mwp=cap_mwp, capacity_mwac=cap, ol=ol, balance_ordering=q("balance_mwp"),
                  inventory=q("inventory_mwp"), receipt=q("receipt_mwp"), under_transit=q("transit_mwp"),
                  lta_date=core._d(proj["lta"]), scod_date=core._d(proj["scod"]))
    prio_now = proj["priority"] if isinstance(proj["priority"], str) and proj["priority"] else "STANDARD"
    multi = len(ph) > 1
    lines = {k: [] for k in ("AI Module Order Date", "AI Order Now", "AI TC Date", "AI TC Date (P90)",
                             "AI FTC (projected)", "AI Risk Level", "AI Days After Deadline", "AI Root Cause")}
    lead_phase, monthly_plan = None, None
    for _, prow in ph.iterrows():
        label, ftc = prow["phase"], core._d(prow["ftc_date"])
        tag = (lambda v: f"{label}: {v}") if multi else (lambda v: str(v))  # noqa: E731
        matched = (proj, prow)
        u2 = core.uc2(core.PriorityRequest(**common, phase=label, ftc_date=ftc, current_priority=prio_now,
                                           vendor_type=vendor, ftc_risk_flag=bool(prow.get("ftc_risk_flag") == 1)),
                      True, matched=matched, use_llm=False)
        u1 = None
        if vendor:
            order_mwp = (_num(prow["order_qty_mwac"]) or 0.0) * ol if ol else q("balance_mwp")
            u1 = core.uc1(core.OrderTcRequest(**common, phase=label, ftc_date=ftc, vendor_type=vendor,
                                              priority=u2["priority_class"]),
                          True, matched=matched, order_mwp=order_mwp, use_llm=False)
            # Project level (the whole balance across phases): the same from any phase.
            monthly_plan = monthly_plan or u1["monthly_requirement"]
            lines["AI Module Order Date"].append(tag(_dmy(u1["order_by_date"]) if u1["order_by_date"]
                                                     else "nothing to order"))
            lines["AI Order Now"].append(tag("Yes" if u1["order_now"] else "No"))
            lines["AI TC Date"].append(tag(_dmy(u1["predicted_tc_date"])))
            lines["AI TC Date (P90)"].append(tag(_dmy(u1["predicted_tc_date_p90"])))
            lines["AI FTC (projected)"].append(tag(_dmy(u1["projected_ftc_date"])))
            lines["AI Risk Level"].append(tag(u1["risk_level"]))
            lines["AI Days After Deadline"].append(tag("-" if u1["deadline_breach_days"] is None
                                                       else u1["deadline_breach_days"]))
            lines["AI Root Cause"].append(tag(u1["root_cause"]["summary"]))
        detail["phases"].append({
            "phase": label, "phase_mwac": _num(prow["phase_mwac"]), "p6_ftc_date": core.iso(ftc),
            "uc2": {k: u2[k] for k in ("priority_class", "priority_score", "reasons", "rule_engine",
                                       "class_probabilities", "realistic_ftc_date", "guardrail")},
            "uc1": None if u1 is None else {k: u1[k] for k in (
                "recommended_order_date", "order_by_date", "order_now", "predicted_tc_date", "predicted_tc_date_p90",
                "projected_ftc_date", "deadline_breach_days", "risk_level", "confidence", "rule_engine",
                "order_by_shift_vs_rule_days", "root_cause", "lead_time")},
            "explanation_uc1": None if u1 is None else u1["explanation"]["text"],
            "explanation_uc2": u2["explanation"]["text"],
        })
        # Lead phase: the first one still to order, else the first pending.
        if lead_phase is None and (u1 is None or u1["order_by_date"]):
            lead_phase = len(detail["phases"]) - 1
    i = lead_phase or 0
    first = detail["phases"][i]
    label, ftc = first["phase"], core._d(ph.iloc[i]["ftc_date"])

    best = max(detail["phases"], key=lambda p: (RANK[p["uc2"]["priority_class"]], p["uc2"]["priority_score"]))
    cols["AI Priority"] = best["uc2"]["priority_class"]
    g = best["uc2"]["guardrail"]
    cols["AI Priority Set By"] = (f"PPA penalty rule (model said {g['model_class']}): {g['reason']}" if g
                                  else "AI model")
    cols["AI Priority Score (model)"] = best["uc2"]["priority_score"]
    cols["Rule Priority (P6 dates)"] = max((p["uc2"]["rule_engine"]["priority_class"] for p in detail["phases"]),
                                           key=RANK.get)
    cols["AI Priority Reasons"] = "; ".join(best["uc2"]["reasons"])
    for k, v in lines.items():
        cols[k] = "\n".join(map(str, v))
    if first["uc1"]:
        lt = first["uc1"]["lead_time"]
        cols["AI Lead Time (P50 / P90 days)"] = f"{lt['ai_p50_days']} / {lt['ai_p90_days']} (rule {lt['rule_engine_days']})"
        cols["AI Confidence"] = first["uc1"]["confidence"]
    cols["AI Explanation - Order & TC (UC1)"] = first["explanation_uc1"] or ""
    cols["AI Explanation - Priority (UC2)"] = best["explanation_uc2"]

    if monthly_plan is not None:
        mr = detail["monthly_requirement"] = monthly_plan
        cols["AI Month wise Module Requirement at Site (MWp / MWac)"] = "\n".join(
            f"{m['month']}: [ {m['required_at_site_mwp']:g} / {m['required_at_site_mwac']:g} ] "
            f"order by {_dmy(m['order_by_date'])}" for m in mr["ai"]["months"]) or "nothing to order"

    notes = []
    if not vendor:
        notes.append(f"Type '{proj['vendor_type']}' has no lead time - priority only")
    if not in_snapshot:
        notes.append("not in the training snapshot - no P6 site pace / planned %")
    if not ol:
        notes.append("no OL - MWp converted with the portfolio median")
    cols["AI Status"] = f"Scored - {len(ph)} phase{'s' if multi else ''}" + (f" ({'; '.join(notes)})" if notes else "")
    detail["lead_phase"] = label
    if explain_jobs_enabled():
        rid = proj["row_id"]
        req1 = core.OrderTcRequest(**common, phase=label, ftc_date=ftc, vendor_type=vendor or "China",
                                   priority=cols["AI Priority"])
        bp = next(p for p in detail["phases"] if p is best)
        bprow = ph.iloc[detail["phases"].index(bp)]
        req2 = core.PriorityRequest(**common, phase=bp["phase"], ftc_date=core._d(bprow["ftc_date"]),
                                    current_priority=prio_now, vendor_type=vendor,
                                    ftc_risk_flag=bool(bprow.get("ftc_risk_flag") == 1))
        prow1 = ph.iloc[i]
        o1 = (_num(prow1["order_qty_mwac"]) or 0.0) * ol if ol else q("balance_mwp")
        if vendor:
            jobs.append((rid, "AI Explanation - Order & TC (UC1)",
                         lambda r=req1, m=(proj, prow1), o=o1: core.uc1(r, True, matched=m, order_mwp=o)))
        jobs.append((rid, "AI Explanation - Priority (UC2)",
                     lambda r=req2, m=(proj, bprow): core.uc2(r, True, matched=m)))
    return {"cols": cols, "detail": detail}


_EXPLAIN = contextvars.ContextVar("batch_explain", default="template")


def explain_jobs_enabled() -> bool:
    return _EXPLAIN.get() == "llm"


def _run(rows, as_of, explain):
    tok = _EXPLAIN.set(explain)
    try:
        return score(rows, as_of, explain)
    finally:
        _EXPLAIN.reset(tok)


def _summary(out: dict) -> dict:
    scored = [v for v in out.values() if v["cols"]["AI Status"].startswith("Scored")]
    return {"projects": len(out), "scored": len(scored),
            "ai_priority": {c: sum(v["cols"]["AI Priority"] == c for v in scored) for c in RANK},
            "order_now": sum("Yes" in v["cols"]["AI Order Now"] for v in scored),
            "high_risk": sum("HIGH" in v["cols"]["AI Risk Level"] for v in scored)}


# ── routes ───────────────────────────────────────────────────────────────────

ExplainMode = Literal["template", "llm", "none"]
EXPLAIN_HELP = ("template: computed explanation, instant (default). llm: the Akasha Copilot writes each "
                "project's lead-phase explanations (slower, needs AI_PROVIDER). none: no explanation text.")


@router.post("/csv", response_class=Response,
             responses={200: {"content": {"text/csv": {}}, "description": "the input CSV with AI columns appended"}})
async def batch_csv(file: UploadFile = File(..., description="Module Deliveries export (.csv)"),
                    explain: ExplainMode = Query("template", description=EXPLAIN_HELP),
                    as_of: Optional[date] = Query(None, description="override the sheet's 'As of' date")):
    rows = rows_from_csv(await file.read())
    md, out = await _in_thread(rows, as_of, explain)
    hdr = P.header_index(rows)
    width = max(len(r) for r in rows)
    res = [r + [""] * (width - len(r)) for r in rows]
    res[hdr] += AI_COLUMNS
    for i in range(len(res)):
        if i != hdr:
            res[i] += [""] * len(AI_COLUMNS)
    for _, m in md.iterrows():
        res[m["_line"]][width:] = [out[m["row_id"]]["cols"][c] for c in AI_COLUMNS]
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(res)
    name = re.sub(r"\.csv$", "", file.filename or "Module Deliveries", flags=re.I) + " - AI.csv"
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/json")
async def batch_json(payload: Any = Body(..., examples=[{"as_of": "2026-10-09", "rows": [{
        "Sr": "4", "Project": "TPL-D PPA", "P6 Name": "ARE8L_A02_HSAT_150MW_PPA_TPL", "EPC Group": "Amara Raja",
        "Category": "PPA", "Type": "ALMM", "Priority": "STANDARD", "OL": "1.35", "Capacity (MWac)": "150",
        "Capacity (MWp)": "203", "LTA": "", "SCOD": "", "Balance Ordering (MWp)": "30",
        "Module Inventory (MWp)": "137", "FTC Date": "07-Nov-26"}]}]),
                     explain: ExplainMode = Query("template", description=EXPLAIN_HELP)):
    """Body: a list of project objects keyed by the Module Deliveries headers
    (line breaks in a header are optional: "Capacity (MWac)"), or
    {"as_of": "YYYY-MM-DD", "rows": [...]}. Optional "EPC Group" groups rows."""
    as_of = None
    if isinstance(payload, dict):
        as_of = date.fromisoformat(str(payload["as_of"])[:10]) if payload.get("as_of") else None
        payload = payload.get("rows") or payload.get("projects")
    rows = rows_from_records(payload)
    md, out = await _in_thread(rows, as_of, explain)
    by_line = {m["_line"]: m["row_id"] for _, m in md.iterrows()}
    data_rows = [i for i, r in enumerate(rows[2:], start=2) if r[0].strip().isdigit()]
    result = []
    for rec, line in zip(payload, data_rows):
        o = out[by_line[line]]
        result.append({**rec, **o["cols"], "ai_detail": o["detail"]})
    return {"as_of": core.iso(date.today()), "data_as_of": core.iso(as_of) if as_of else None,
            "summary": _summary(out), "columns_added": AI_COLUMNS, "rows": result,
            "label": "AI forecast - inferred from P6 dates, site progress and measured lead times, not a plan "
                     "or SAP figure"}


async def _in_thread(rows, as_of, explain):
    import anyio
    ctx = contextvars.copy_context()
    return await anyio.to_thread.run_sync(lambda: ctx.run(_run, rows, as_of, explain))
