"""Site productivity from P6 block progress, and what it means for module ordering.

Modules are only useful once the tracker under them is built, so ordering has
to follow the site's real pace: a fast site with modules not ordered will stall,
a slow site with modules arriving builds idle stock. This module measures that
pace and the front ready for modules.

What P6 gives (checked 2026-10-09, latest schedule per project):
- Every block carries the same construction activities ("Block-07 -MMS
  Erection - Purlin"), 986 blocks across 54 projects, each with a planned and
  actual quantity (Material, "... - Construction": piles Nos, tables TBL,
  module MWdc) and actual start / finish dates.
- P6's actual manpower is NOT a site measurement: on 916 of 1,358 progressed
  activities labour % equals quantity % exactly (median ratio 1.00), i.e. it
  is derived from progress. So "units per manday" is never computed from P6;
  the site norms below (user-supplied, HSAT / FT) are used instead, to turn the
  remaining work into the manpower needed per day.

- Quantity units are not uniform across projects (purlin is ~1,485 per block
  on some schedules vs ~365 tables for torque tube), so manpower is computed
  from the norm "mandays for 1 MWac" x the MWac still to do, never from raw
  P6 quantities divided by a per-unit norm.

Pace is MEASURED: quantity done / days from the activity's first actual start
to the schedule's data date (not today: a schedule not updated for weeks would
otherwise read as a stalled site). It is an average since start, and the
predicted finish (what is left / that pace) is inference; both are labelled.
"""
import re
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session



# Site productivity norms (user, 2026-10-09). Per activity and MMS type:
# scope for one block, effort weight, mandays for 1 MWac, and productivity in
# units per manday (the sheet's "Productivity" column: 3,197 piles / 9.51 =
# 336 mandays = 27 mandays/MWac x 12.4 MWac per block, so it is units per
# manday, not mandays per unit).
NORMS: dict[str, dict] = {
    "pile_tracker": {"code": "01a", "label": "Piles for tracker structure", "uom": "piles", "area": "piling",
                     "HSAT": (3197, 0.074, 27, 9.51), "FT": (6200, 0.115, 45, 11.07)},
    "pile_inverter": {"code": "01b", "label": "Piles for inverters", "uom": "piles", "area": "piling",
                      "HSAT": (92, 0.003, 1, 7.67), "FT": (92, 0.002, 1, 7.67)},
    "pile_docking": {"code": "03", "label": "Piles for robot docking stations", "uom": "piles", "area": "piling",
                     "HSAT": (44, 0.002, 1, 4.40), "FT": (44, 0.002, 1, 4.40)},
    "tracker_tt": {"code": "04", "label": "Structure: torque tube / rafter", "uom": "tables", "area": "tracker",
                   "HSAT": (279, 0.245, 90, 0.25), "FT": (494, 0.101, 39, 1.01)},
    "tracker_ts": {"code": "05", "label": "Structure: transmission shaft / bracing", "uom": "tables", "area": "tracker",
                   "HSAT": (279, 0.153, 56, 0.40), "FT": (494, 0.092, 36, 1.10)},
    "tracker_purlin": {"code": "06", "label": "Structure: purlin (ready for modules)", "uom": "tables", "area": "tracker",
                       "HSAT": (279, 0.123, 45, 0.50), "FT": (494, 0.288, 112, 0.35)},
    "module": {"code": "07", "label": "Modules mounted", "uom": "MWdc", "area": "module",
               "HSAT": (17, 0.125, 46, 0.030), "FT": (17, 0.137, 53, 0.025)},
}
# 02. Messenger Support Piling has no block activity in P6, so it is not tracked.

# P6 block activity (text after "Block-NN -") -> norm key.
ACTIVITY_PATTERNS = [
    ("pile_tracker", re.compile(r"^piling - mms", re.I)),
    ("pile_inverter", re.compile(r"^piling - inverters?", re.I)),
    ("pile_docking", re.compile(r"^piling - robotic docking", re.I)),
    ("tracker_tt", re.compile(r"^mms erection - torque tube", re.I)),
    ("tracker_ts", re.compile(r"^mms erection - transmission shaft", re.I)),
    ("tracker_purlin", re.compile(r"^mms erection - purlin", re.I)),
    ("module", re.compile(r"^module installation\s*$", re.I)),
]
AREAS = {
    "piling": {"label": "Piles installed", "keys": ["pile_tracker", "pile_inverter", "pile_docking"], "gate": "pile_tracker"},
    # A block's tracker is done when its purlin is done - the last tracker step.
    "tracker": {"label": "Structure built (tracker)", "keys": ["tracker_tt", "tracker_ts", "tracker_purlin"], "gate": "tracker_purlin"},
    "module": {"label": "Modules mounted", "keys": ["module"], "gate": "module"},
}
FORECAST_MAX_DAYS = 730
_BLOCK = re.compile(r"^\s*block[- ]?(\d+[a-z]?)\s*-\s*(.+?)\s*$", re.I)

LATEST_P6 = """
    SELECT DISTINCT ON (project_id) project_id, p6_object_id, data_date
    FROM p6_project
    WHERE project_id IS NOT NULL
    ORDER BY project_id, data_date DESC NULLS LAST, last_synced_at DESC NULLS LAST, p6_object_id DESC
"""


def mms_kind(mms_type: Optional[str], p6_name: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """(HSAT | FT | None, source). The project master's MMS type first; where
    it is blank, the type the P6 name states (ARE55L_A18_HSAT_600MW_PPA)."""
    t = (mms_type or "").strip().upper()
    if "HSAT" in t:
        return "HSAT", "project master"
    if t.startswith("FT") or "FIXED" in t:
        return "FT", "project master"
    tokens = set(re.split(r"[_\s-]+", (p6_name or "").upper()))
    if "HSAT" in tokens:
        return "HSAT", "P6 name"
    if "FT" in tokens:
        return "FT", "P6 name"
    return None, None


def load_blocks(db: Session) -> dict:
    """{project_id: {"data_date": dt, "blocks": {block: {key: activity}}}} from
    the latest P6 schedule of each project. activity = planned / actual
    construction quantity and actual start / finish."""
    rows = db.execute(text(f"""
        WITH latest AS ({LATEST_P6})
        SELECT l.project_id, l.data_date, a.name, a.actual_start_date, a.actual_finish_date,
               SUM(r.planned_units) FILTER (WHERE r.resource_name ILIKE '%construction%'),
               SUM(r.actual_units) FILTER (WHERE r.resource_name ILIKE '%construction%'),
               a.baseline_start_date, a.baseline_finish_date, a.planned_start_date, a.planned_finish_date
        FROM latest l
        JOIN p6_activity a ON a.project_object_id = l.p6_object_id
        LEFT JOIN p6_resource_assignment r ON r.activity_object_id = a.p6_object_id AND r.resource_type = 'Material'
        WHERE a.name ~* '^\\s*block[- ]?\\d+'
        GROUP BY 1, 2, 3, 4, 5, 8, 9, 10, 11""")).fetchall()
    out: dict = {}
    for pid, data_date, name, a_start, a_finish, planned, actual, b_start, b_finish, p_start, p_finish in rows:
        m = _BLOCK.match(name or "")
        if not m:
            continue
        rest = re.sub(r"\s+", " ", m.group(2))
        key = next((k for k, pat in ACTIVITY_PATTERNS if pat.match(rest)), None)
        if not key:
            continue
        proj = out.setdefault(pid, {"data_date": data_date, "blocks": defaultdict(dict)})
        proj["blocks"][m.group(1).upper().lstrip("0") or "0"][key] = {
            "planned": float(planned or 0), "actual": float(actual or 0), "start": a_start, "finish": a_finish,
            # The commitment: baseline dates, else the current plan's.
            "plan_start": b_start if b_start and b_finish else p_start,
            "plan_finish": b_finish if b_start and b_finish else p_finish,
            "current_finish": p_finish}
    return out


def _plan_frac(a: dict, on: datetime) -> Optional[float]:
    """Share of the activity the baseline expected done by `on` (linear
    between its baseline start and finish). None without plan dates."""
    s, f = a.get("plan_start"), a.get("plan_finish")
    if not s or not f:
        return None
    if on >= f:
        return 1.0
    if on <= s:
        return 0.0
    span = (f - s).total_seconds()
    return (on - s).total_seconds() / span if span > 0 else 1.0


def _frac(a: dict) -> float:
    """Share of an activity done: quantity where P6 has one, else 1 when finished."""
    if a["planned"] > 0:
        return min(a["actual"] / a["planned"], 1.0)
    return 1.0 if a["finish"] else 0.0


def project_productivity(proj: Optional[dict], share: float, mms_type: Optional[str], p6_name: Optional[str],
                         cap_mwac: float, final_ftc: Optional[datetime]) -> Optional[dict]:
    """Per activity and per area (piling / tracker / module): scope, done, %,
    average pace since start, pace required to the final pending FTC, and
    manpower needed per day at the norm. Plus the module front ready. Block
    quantities are scaled by `share` when several project rows share one P6
    schedule; cap_mwac is this row's capacity."""
    if not proj or not proj["blocks"]:
        return None
    dd: datetime = proj["data_date"] or datetime.utcnow()
    kind, kind_source = mms_kind(mms_type, p6_name)
    days_to_ftc = (final_ftc.date() - dd.date()).days if final_ftc else None
    blocks = proj["blocks"]

    def pace_of(acts: list, done_qty: float, remaining: float) -> tuple[float, Optional[int]]:
        starts = [a["start"] for a in acts if a["start"]]
        if not starts or done_qty <= 0:
            return 0.0, None
        end = dd if remaining > 0 else max((a["finish"] for a in acts if a["finish"]), default=dd)
        span = max((end.date() - min(starts).date()).days, 1)
        return done_qty / span, span

    activities = []
    for key, norm in NORMS.items():
        acts = [b[key] for b in blocks.values() if key in b]
        if not acts:
            continue
        planned = sum(a["planned"] for a in acts) * share
        done = sum(a["planned"] * _frac(a) if a["planned"] > 0 else 0.0 for a in acts) * share
        frac_done = sum(_frac(a) for a in acts) / len(acts)
        plan_fr = [x for x in (_plan_frac(a, dd) for a in acts) if x is not None]
        plan_pct = round(sum(plan_fr) / len(plan_fr) * 100, 1) if plan_fr else None
        remaining = max(planned - done, 0.0)
        pace, span = pace_of(acts, done, remaining)
        md_per_mwac = norm[kind][2] if kind else None
        mandays_left = (1 - frac_done) * cap_mwac * md_per_mwac if md_per_mwac and cap_mwac > 0 else None
        activities.append({
            "key": key, "code": norm["code"], "label": norm["label"], "area": norm["area"], "uom": norm["uom"],
            "blocks": len(acts), "blocks_done": sum(1 for a in acts if a["finish"]),
            "planned": round(planned, 1), "done": round(done, 1),
            "pct": round(frac_done * 100, 1),
            # What the baseline expected done by the P6 data date, and the gap.
            "plan_pct": plan_pct,
            "behind_pts": round(plan_pct - frac_done * 100, 1) if plan_pct is not None else None,
            "pace_per_day": round(pace, 2), "pace_days": span,
            "required_per_day": round(remaining / days_to_ftc, 2) if days_to_ftc and days_to_ftc > 0 and remaining > 0 else None,
            "days_to_finish": 0 if remaining <= 0 else (round(remaining / pace) if pace > 0 else None),
            "norm_units_per_manday": norm[kind][3] if kind else None,
            "norm_mandays_per_mwac": md_per_mwac,
            "mandays_left": round(mandays_left) if mandays_left else None,
            "manpower_needed_per_day": round(mandays_left / days_to_ftc) if mandays_left and days_to_ftc and days_to_ftc > 0 else None,
        })

    # Each block's module MWdc is the common currency across areas.
    def mod_mw(b):
        return b.get("module", {}).get("planned", 0.0)
    total_mw = sum(mod_mw(b) for b in blocks.values()) * share
    areas = {}
    for akey, a in AREAS.items():
        gate = a["gate"]
        gated = [b for b in blocks.values() if gate in b]
        acts = [x for x in activities if x["area"] == akey]
        if not gated or not acts:
            continue
        done_mw = sum(mod_mw(b) * _frac(b[gate]) for b in gated) * share
        left = max(total_mw - done_mw, 0.0)
        pace, span = pace_of([b[gate] for b in gated], done_mw, left)
        # Area % weighted by the norm effort weights (equal weights when the
        # MMS type is unknown).
        w = [(NORMS[x["key"]][kind][1] if kind else 1.0, x["pct"]) for x in acts]
        pct = round(sum(wi * p for wi, p in w) / sum(wi for wi, _ in w), 1)
        wp = [(NORMS[x["key"]][kind][1] if kind else 1.0, x["plan_pct"]) for x in acts if x["plan_pct"] is not None]
        plan_pct = round(sum(wi * p for wi, p in wp) / sum(wi for wi, _ in wp), 1) if wp else None
        # When P6's current schedule has this stage finishing (latest block).
        cur = [b[gate]["current_finish"] for b in gated if b[gate].get("current_finish")]
        p6_finish = max(cur) if cur else None
        finish = dd if left <= 0.05 else (dd + timedelta(days=left / pace) if pace > 0 else None)
        need = [x["manpower_needed_per_day"] for x in acts if x["manpower_needed_per_day"]]
        mandays = [x["mandays_left"] for x in acts if x["mandays_left"]]
        areas[akey] = {
            "label": a["label"], "pct": pct,
            "blocks": len(gated), "blocks_done": sum(1 for b in gated if b[gate]["finish"]),
            "done_mwdc": round(done_mw, 1), "pace_mwdc_per_day": round(pace, 2), "pace_days": span,
            "required_mwdc_per_day": round(left / days_to_ftc, 2) if days_to_ftc and days_to_ftc > 0 and left > 0.05 else None,
            "predicted_finish": finish.date().isoformat() if finish else None,
            "plan_pct": plan_pct,
            "behind_pts": round(plan_pct - pct, 1) if plan_pct is not None else None,
            "p6_finish": p6_finish.date().isoformat() if p6_finish else None,
            # Site-speed finish against P6's own plan for this stage.
            "late_days": (finish.date() - p6_finish.date()).days if finish and p6_finish and left > 0.05 else (0 if left <= 0.05 else None),
            "mandays_left": sum(mandays) if mandays else None,
            "manpower_needed_per_day": sum(need) if need else None,
        }

    # Forecast FTC: the P6 FTC moved by how late the site's speed puts the
    # latest stage that is moving (modules, else structure, else piles)
    # against P6's own plan for that stage. An estimate, labelled as one.
    # The stage running latest against plan sets it: a later stage cannot
    # finish before the one it stands on. Beyond two years late the average
    # speed says only "far too slow", so no date is printed for it.
    ftc_forecast, ftc_delay, ftc_driver, ftc_note = None, None, None, None
    if final_ftc:
        moving = [(a["late_days"], a["label"]) for k in ("piling", "tracker", "module")
                  if (a := areas.get(k)) and a["pct"] < 99.5 and a["late_days"] is not None and a["pace_mwdc_per_day"] > 0]
        if moving:
            late, ftc_driver = max(moving)
            ftc_delay = max(late, 0)
            if ftc_delay > FORECAST_MAX_DAYS:
                ftc_note = f"{ftc_driver} is moving too slowly to forecast: at today's speed it finishes more than two years late."
                ftc_delay = None
            else:
                ftc_forecast = (final_ftc + timedelta(days=ftc_delay)).date().isoformat()

    front = sum(max(mod_mw(b) - b.get("module", {}).get("actual", 0.0), 0.0)
                for b in blocks.values() if b.get("tracker_purlin", {}).get("finish")) * share
    return {
        "data_date": dd.date().isoformat(),
        "data_age_days": (datetime.utcnow().date() - dd.date()).days,
        "mms_kind": kind, "mms_source": kind_source,
        "final_ftc": final_ftc.date().isoformat() if final_ftc else None,
        "days_to_ftc": days_to_ftc,
        "blocks": len(blocks), "module_scope_mwdc": round(total_mw, 1),
        "front_ready_mwdc": round(front, 1),
        "ftc_forecast": ftc_forecast, "ftc_delay_days": ftc_delay, "ftc_driver": ftc_driver, "ftc_note": ftc_note,
        "areas": areas, "activities": activities,
    }


def ordering_signal(prod: Optional[dict], *, modules_at_site_mwp: float, in_transit_mwp: float,
                    balance_ordering_mwp: float, lead_time_days: int) -> dict:
    """What the site's pace means for module ordering. First match wins:

    records_conflict  P6 shows more modules erected than SAP received - the
                      supply figures cannot be read until that is reconciled
    modules_short     tracker complete without modules > modules at site:
                      erection will wait for modules
    order_now         at its measured pace the tracker finishes before an
                      order placed today can arrive, and capacity is unordered
    stock_building    modules at site + in transit exceed the front ready plus
                      60 days of tracker output
    complete          modules mounted on every block
    not_started       no piles, no structure and no modules at site yet
    piling_only       piles going in, structure not started, no modules at site
    on_track          none of the above: supply matches the site
    no_progress       P6 has no block-level structure activities"""
    if not prod or "tracker" not in prod["areas"]:
        return {"state": "no_progress", "text": "No P6 site data",
                "detail": "P6 has no block-by-block progress for piles, structure or modules on this project, so the site cannot be compared with module supply.",
                "action": "Ask the project planner to load block-level progress into P6."}
    trk = prod["areas"]["tracker"]
    mod = prod["areas"].get("module")
    front = prod["front_ready_mwdc"]
    if modules_at_site_mwp < -1:
        return {"state": "records_conflict", "text": "Data mismatch: SAP vs P6",
                "detail": f"P6 says {-modules_at_site_mwp:,.1f} MWp more modules are mounted than SAP shows as received. One of the two is out of date, so the module stock cannot be trusted.",
                "action": "Check with stores and the site team which figure is right, and correct SAP receipts or P6 progress before deciding on more orders."}
    at_site = max(modules_at_site_mwp, 0.0)
    if front > at_site + 1:
        gap = front - at_site
        return {"state": "modules_short", "text": f"Modules short · {gap:,.0f} MWp",
                "detail": f"Structures for {front:,.1f} MWdc are finished and waiting for panels, but only {at_site:,.1f} MWp of modules is in the yard. Mounting crews will run out of work.",
                "action": f"Speed up dispatch and goods receipt of about {gap:,.0f} MWp. If nothing is on the way, raise the order now."}
    if balance_ordering_mwp > 0.5 and trk["predicted_finish"] and (mod is None or mod["pct"] < 99):
        finish = datetime.fromisoformat(trk["predicted_finish"]).date()
        arrive = datetime.utcnow().date() + timedelta(days=lead_time_days)
        if arrive > finish:
            return {"state": "order_now", "text": f"Order now · {balance_ordering_mwp:,.0f} MWp",
                    "detail": f"At today's speed the structures will be finished around {finish:%d-%b-%y}. A module order placed today would only arrive around {arrive:%d-%b-%y} ({lead_time_days} days lead time), and {balance_ordering_mwp:,.1f} MWp is still not ordered.",
                    "action": f"Place the order for the remaining {balance_ordering_mwp:,.0f} MWp now, so the structures do not stand empty."}
    absorb = front + trk["pace_mwdc_per_day"] * 60
    supply = at_site + max(in_transit_mwp, 0.0)
    if supply > absorb + 5:
        excess = supply - absorb
        return {"state": "stock_building", "text": f"Excess modules · {excess:,.0f} MWp",
                "detail": f"{supply:,.1f} MWp of modules is in the yard or on the way, but only {front:,.1f} MWdc of structure is ready, and the site builds about {trk['pace_mwdc_per_day']:,.2f} MWdc of structure a day. Around {excess:,.0f} MWp will sit in the yard for more than two months.",
                "action": "Hold further dispatches or the next order for this project, and push structure work (steel supply, crews) so the modules can be mounted."}
    pile = prod["areas"].get("piling")
    if mod and mod["pct"] >= 99.5 and front < 1:
        return {"state": "complete", "text": "Modules complete",
                "detail": "Modules are mounted on every block in P6.",
                "action": "Nothing for modules. Any balance still showing is a records gap, not a need."}
    if trk["pct"] < 1 and at_site < 1 and supply < 1:
        if pile and pile["pct"] >= 1:
            return {"state": "piling_only", "text": "Piling in progress",
                    "detail": f"Piles are {pile['pct']:.0f}% installed, the structure has not started and no modules are at site. That is the right order of work.",
                    "action": "No modules needed yet. Plan the order so modules arrive when the first structures are finished."}
        return {"state": "not_started", "text": "Not started",
                "detail": "No piles, structure or modules yet in P6, and no modules at site.",
                "action": "Nothing to do for modules yet."}
    return {"state": "on_track", "text": "Supply matches site",
            "detail": "The modules in the yard and on the way match the structures that are ready and the speed they are being built: no shortage and no excess.",
            "action": "Keep the current dispatch plan."}
