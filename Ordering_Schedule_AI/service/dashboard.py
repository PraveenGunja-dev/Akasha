"""AI fields for the Akasha Ordering Schedule dashboard export.

    POST /api/ai/v1/batch/akasha-dashboard        multipart file -> JSON
    POST /api/ai/v1/batch/akasha-dashboard/json   JSON body      -> JSON

Input is the dashboard export (akasha_ordering_schedule_full.json: the JSON of
GET /akasha/api/module-deliveries/summary + block-plan). Every project in
ordering_schedule.projects gets AI fields from the two use cases - the same
code as POST /order-tc-forecast?explain=true (UC1) and
POST /priority-predict?explain=true (UC2), called in-process rather than over
HTTP. Each project gets exactly two fields:
ai_priority (the UC2 response) and ai_monthly_order_tc_forecast (the UC1
response); everything else in the document is returned unchanged. The result is
also written to data/output/AIAkashaOrderingSchedule_final.json.

Field mapping (dashboard -> use-case request): p6_name -> project_id,
type -> vendor_type, capacity_mwp/mwac, ol, balance_ordering_mwp,
module_inventory_mwp (negative values clamp to 0), total_receipt_mwp,
under_transit_mwp, lta, scod, and each phase of ftc_date
("Ph-I (150MW): 09-Dec-26 · Ph-II (150MW): 03-Jan-27") -> ftc_date + phase.
The balance is funded across phases by the Planning Rules sequence, so each
phase's own order quantity sets whether it still needs ordering.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Body, File, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

import monthly
from features import RULE_LEAD_DAYS

from . import app as core
from .engine import ROOT

router = APIRouter(prefix=f"{core.PREFIX}/batch/akasha-dashboard", tags=["batch"])
OUTPUT_DIR = ROOT / "data" / "output"
RANK = {"P1": 2, "P2": 1, "STANDARD": 0}
PHASE_RE = re.compile(r"^(?P<label>.+?)\s*\((?P<mw>[\d.]+)\s*MW\)(?P<extra>[^:]*):\s*(?P<date>\d{2}-[A-Z][a-z]{2}-\d{2})$")


def _date(s) -> Optional[date]:
    s = (s or "").strip()
    try:
        return datetime.strptime(s, "%d-%b-%y").date() if s else None
    except ValueError:
        return None


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return 0.0
    return v if v == v else 0.0


def phases_of(p: dict) -> list[dict]:
    """ftc_date -> [{label, mwac, ftc}]. A bare date is one phase of full capacity."""
    out = []
    for part in [s.strip() for s in (p.get("ftc_date") or "").split("·") if s.strip()]:
        m = PHASE_RE.match(part)
        if m:
            label = re.sub(r"\s+", " ", (m.group("label") + m.group("extra")).strip())
            out.append({"label": label, "mwac": float(m.group("mw")), "ftc": _date(m.group("date"))})
        elif _date(part):
            out.append({"label": "Single phase", "mwac": _num(p.get("capacity_mwac")), "ftc": _date(part)})
    return [ph for ph in out if ph["ftc"]]


def _category(p: dict) -> str:
    c = (p.get("category") or "").strip().upper()
    return c if c in ("PPA", "MERCHANT", "GROUP") else ""


def _not_scored(reason: str) -> dict:
    return {"status": "not_scored", "reason": reason}


def score_project(p: dict, dup_p6: set) -> tuple[dict, Optional[tuple]]:
    """The two AI fields for one dashboard project, and the lead-phase UC1 job (for LLM mode)."""
    ai: dict[str, Any] = {}
    phases = phases_of(p)
    if p.get("ftc_all_charged") or not phases:
        why = "all FTC phases charged" if p.get("ftc_all_charged") else "no pending FTC date"
        return {"ai_priority": _not_scored(why), "ai_monthly_order_tc_forecast": _not_scored(why)}, None

    notes = []
    vendor = next((k for k in RULE_LEAD_DAYS if k.lower() == (p.get("type") or "").lower()), None)
    ol = _num(p.get("ol")) or None
    cap_ac = _num(p.get("capacity_mwac"))
    cap_p = _num(p.get("capacity_mwp")) or (cap_ac * ol if ol else cap_ac * core.ENGINE.median_ol)
    if not vendor:
        notes.append(f"type '{p.get('type') or 'blank'}' has no lead time - priority only")
    if not ol:
        notes.append("OL missing - MWp converted with the portfolio median")
    if p.get("p6_name") in dup_p6:
        notes.append("P6 name appears on more than one dashboard row - check the project mapping")
    if _num(p.get("module_inventory_mwp")) < 0:
        notes.append("negative SAP inventory treated as 0")
    if not cap_ac:
        return {"ai_priority": _not_scored("no capacity"), "ai_monthly_order_tc_forecast": _not_scored("no capacity")}, None

    common = dict(project_id=p.get("p6_name") or p.get("project_name"), project_name=p.get("project_name") or "",
                  capacity_mwp=cap_p, capacity_mwac=cap_ac, ol=ol,
                  balance_ordering=max(_num(p.get("balance_ordering_mwp")), 0.0),
                  inventory=max(_num(p.get("module_inventory_mwp")), 0.0),
                  receipt=max(_num(p.get("total_receipt_mwp")), 0.0),
                  under_transit=max(_num(p.get("under_transit_mwp")), 0.0),
                  lta_date=_date(p.get("lta")), scod_date=_date(p.get("scod")))
    current = (p.get("priority") or "STANDARD").upper()
    # Planning Rules funding: each phase's own share of the balance.
    funded = {ph.label: q for ph, q in monthly.fund(
        [monthly.Phase(x["label"], x["mwac"], x["ftc"]) for x in phases],
        common["balance_ordering"] / (ol or core.ENGINE.median_ol), RULE_LEAD_DAYS.get(vendor))}

    rows, lead, lead_uc1, lead_req = [], None, None, None
    req2s = {}
    for ph in phases:
        req2s[ph["label"]] = core.PriorityRequest(**common, phase=ph["label"], ftc_date=ph["ftc"],
                                                  category=_category(p), current_priority=current, vendor_type=vendor)
        u2 = core.uc2(req2s[ph["label"]], True, use_llm=False)
        u1 = None
        if vendor:
            req = core.OrderTcRequest(**common, phase=ph["label"], ftc_date=ph["ftc"], vendor_type=vendor,
                                      priority=u2["priority_class"], category=_category(p))
            order_mwp = funded.get(ph["label"], 0.0) * (ol or core.ENGINE.median_ol)
            u1 = core.uc1(req, True, order_mwp=order_mwp, use_llm=False)
            if lead is None and u1["order_by_date"]:
                lead, lead_uc1, lead_req = ph, u1, (req, order_mwp)
        rows.append((ph, u1, u2))
    if vendor and lead is None:   # nothing left to order: the first pending phase leads
        lead, lead_uc1 = rows[0][0], rows[0][1]
        lead_req = (core.OrderTcRequest(**common, phase=lead["label"], ftc_date=lead["ftc"], vendor_type=vendor,
                                        priority=rows[0][2]["priority_class"], category=_category(p)), 0.0)

    # ai_priority: the UC2 response for the project's most urgent phase, with
    # every phase's class and the data notes alongside.
    ph_b, _, u2_b = max(rows, key=lambda r: (RANK[r[2]["priority_class"]], r[2]["priority_score"]))
    ai["ai_priority"] = {
        "status": "scored", "phase": ph_b["label"], "notes": notes,
        **{k: v for k, v in u2_b.items() if k != "project"},
        "phases": [{"phase": ph["label"], "p6_ftc_date": ph["ftc"].isoformat(),
                    "priority_class": u2["priority_class"], "priority_score": u2["priority_score"],
                    "realistic_ftc_date": u2["realistic_ftc_date"],
                    "rule_engine_priority": u2["rule_engine"]["priority_class"]} for ph, _, u2 in rows],
    }

    # ai_monthly_order_tc_forecast: the UC1 response for the lead phase (first
    # one still to order), with every phase's order / TC dates alongside.
    if vendor:
        ai["ai_monthly_order_tc_forecast"] = {
            "status": "scored", "phase": lead["label"], "notes": notes,
            **{k: v for k, v in lead_uc1.items() if k != "project"},
            "phases": [{"phase": ph["label"], "p6_ftc_date": ph["ftc"].isoformat(),
                        **{k: u1[k] for k in ("order_by_date", "recommended_order_date", "order_now",
                                              "predicted_tc_date", "predicted_tc_date_p90", "projected_ftc_date",
                                              "deadline_breach_days", "risk_level", "rule_engine")}}
                       for ph, u1, _ in rows],
        }
    else:
        ai["ai_monthly_order_tc_forecast"] = _not_scored(notes[0])
    return ai, {"uc1": lead_req if vendor else None, "uc2": req2s[ph_b["label"]]}


def enrich(doc: dict, explain: str) -> dict:
    try:
        projects = doc["ordering_schedule"]["projects"]
        assert isinstance(projects, list)
    except (KeyError, TypeError, AssertionError):
        raise HTTPException(422, "expected the dashboard export: {\"ordering_schedule\": {\"projects\": [...]}}")
    counts = Counter(p.get("p6_name") for p in projects if p.get("p6_name"))
    dup = {k for k, n in counts.items() if n > 1}
    jobs = []
    for i, p in enumerate(projects):
        try:
            ai, job = score_project(p, dup)
        except HTTPException as e:   # one bad row must not sink the file
            ai = {"ai_priority": _not_scored(str(e.detail)), "ai_monthly_order_tc_forecast": _not_scored(str(e.detail))}
            job = None
        p.update(ai)
        if job and explain == "llm":
            jobs.append((i, job))
    if explain == "llm" and jobs:
        # Copilot explanations for each project's reported phases; rate limits keep the pool small.
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = []
            for i, job in jobs:
                if job["uc1"]:
                    req, om = job["uc1"]
                    futs.append((i, "ai_monthly_order_tc_forecast", pool.submit(core.uc1, req, True, None, om, True)))
                futs.append((i, "ai_priority", pool.submit(core.uc2, job["uc2"], True, None, True)))
            retry = []
            for i, field, f in futs:
                try:
                    projects[i][field]["explanation"] = f.result()["explanation"]
                except Exception:  # noqa: BLE001 - template explanation stands
                    pass
                if projects[i][field]["explanation"]["mode"] != "llm":
                    retry.append((i, field))
        # Second pass, one at a time: whatever the provider's rate limit turned back.
        for i, field in retry:
            job = dict(jobs)[i]
            try:
                if field == "ai_priority":
                    e = core.uc2(job["uc2"], True, None, True)["explanation"]
                else:
                    req, om = job["uc1"]
                    e = core.uc1(req, True, None, om, True)["explanation"]
                if e["mode"] == "llm":
                    projects[i][field]["explanation"] = e
            except Exception:  # noqa: BLE001 - template explanation stands
                pass
    if explain == "none":
        for p in projects:
            p["ai_monthly_order_tc_forecast"].pop("explanation", None)
            p["ai_priority"].pop("explanation", None)

    prio = [p["ai_priority"] for p in projects if p["ai_priority"]["status"] == "scored"]
    uc1 = [p["ai_monthly_order_tc_forecast"] for p in projects
           if p["ai_monthly_order_tc_forecast"]["status"] == "scored"]
    doc.setdefault("meta", {})["ai"] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "Ordering Schedule AI - ai_monthly_order_tc_forecast = UC1 order-tc-forecast?explain=true, "
                  "ai_priority = UC2 priority-predict?explain=true",
        "explanation_mode": explain,
        "fields_added": ["ai_priority", "ai_monthly_order_tc_forecast"],
        "notes": "Each field is the use-case response for one phase ('phase'); 'phases' lists every pending phase. "
                 "status 'not_scored' carries a 'reason'. Dates are ISO 'YYYY-MM-DD'.",
        "summary": {"projects": len(projects), "priority_scored": len(prio), "order_tc_scored": len(uc1),
                    "ai_priority": {c: sum(x["priority_class"] == c for x in prio) for c in RANK},
                    "order_now": sum(bool(x["order_now"]) for x in uc1),
                    "high_risk": sum(x["risk_level"] == "HIGH" for x in uc1)},
        "models": {"trained_at": core.ENGINE.meta["trained_at"], "data_as_of": core.ENGINE.meta["data_as_of"]},
        "label": "AI forecast - inferred from P6 dates, site progress and measured lead times; not a plan or SAP "
                 "figure",
    }
    return doc


OUTPUT_NAME = "AIAkashaOrderingSchedule_final.json"


def _save(doc: dict, name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^\w.-]+", "_", Path(name or OUTPUT_NAME).stem)
    path = OUTPUT_DIR / f"{stem}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _respond(doc: dict, path: Path) -> JSONResponse:
    return core.UTF8JSONResponse(doc, headers={
        "Content-Disposition": f'attachment; filename="{path.name}"',
        "X-Output-Path": str(path.relative_to(ROOT)).replace("\\", "/")})


ExplainMode = Literal["template", "llm", "none"]
EXPLAIN_HELP = ("Explanations for both use cases: template (default, instant), llm (copilot per project - slow "
                "on the Groq free tier), none.")
NAME_HELP = "file name under data/output/"


@router.post("")
async def akasha_dashboard_file(file: UploadFile = File(..., description="akasha_ordering_schedule_full.json"),
                                explain: ExplainMode = Query("template", description=EXPLAIN_HELP),
                                output_name: str = Query(OUTPUT_NAME, description=NAME_HELP)):
    """Upload the dashboard export; returns it with ai_priority and ai_monthly_order_tc_forecast on
    every project and saves data/output/AIAkashaOrderingSchedule_final.json."""
    try:
        doc = json.loads((await file.read()).decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise HTTPException(422, f"not a JSON file: {e}")
    doc = await _in_thread(doc, explain)
    return _respond(doc, _save(doc, output_name))


@router.post("/json")
async def akasha_dashboard_json(doc: dict = Body(..., description="the dashboard export JSON"),
                                explain: ExplainMode = Query("template", description=EXPLAIN_HELP),
                                output_name: str = Query(OUTPUT_NAME, description=NAME_HELP)):
    """The same, for a frontend that posts the export as JSON."""
    doc = await _in_thread(doc, explain)
    return _respond(doc, _save(doc, output_name))


async def _in_thread(doc, explain):
    import anyio
    return await anyio.to_thread.run_sync(lambda: enrich(doc, explain))
