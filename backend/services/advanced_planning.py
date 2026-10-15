"""Advanced AI planning for module ordering (branch orderingpoc).

The Ordering Schedule times each FTC phase's whole balance against its FTC
milestone. This plans the way a site actually consumes modules: block by
block, as each block's structure gets ready.

Per block, the stage chain P6 carries for every solar block (54 projects,
986 blocks, checked 2026-10-11):

    Piling - MMS -> Pile capping -> Torque tube / rafter
      -> Transmission shaft / bracing -> Purlin -> Module installation

Pile capping finishes the pile head the structure is fixed to: it starts a
median 19 days after piling and 54 days before torque tube, so "capping done"
is the piles-ready gate (P6 has no pile inspection activity).  MMS RFI
completion has no actual date on any block, so purlin finish is taken as
structure ready.

For each block and stage:
  * progress  - quantity done / planned (P6 Material "... - Construction"),
                else P6 % complete;
  * delay     - forecast finish vs the ASSIGNED P6 baseline (projects without
                an assigned baseline get no delay figure);
  * forecast  - measured, not planned: an in-progress stage runs at its own
                pace so far (or the project's typical duration for that stage
                when it has barely started); a stage not started begins after
                its predecessor by the gap this project's blocks actually show
                and takes the duration they actually took.  Estimates, labelled.

Modules are needed 14 days before a block's forecast module installation
start (site receipt and inspection buffer).  Supply - ordered, delivered,
in transit, erected - is the Ordering Schedule's own project figures, netted
block by block in need order; a block left short gets an order-by date of
need date minus the origin's lead time.

Blocks are grouped under their FTC phase: each block's own "First Time
Charging" milestone falls on or before the phase FTC it charges in, so a
block belongs to the first phase FTC on or after its own.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from services import ai_prediction, site_weather
from services.module_planner import CAP_LIMITS, DEFAULT_CAP, DEFAULT_LEAD_TIME, LEAD_TIMES, PRIORITY_RANKS

SITE_BUFFER_DAYS = 14          # modules on site this long before installation starts
MIN_SAMPLES = 3                # completed blocks needed to trust a project's own figure
OWN_PACE_MIN_FRAC = 0.2        # below this, an in-progress stage's own pace is too noisy
PAUSED_FACTOR = 2.0            # open longer than 2x its expected duration = paused, not slow
FORECAST_CAP_DAYS = 730
SHORT_TOLERANCE_MWP = 0.5      # below this a block's gap is SAP-vs-P6 rounding, not a shortage
RECENT_DAYS = 30               # "blocks completed in the last 30 days" = site speed

STAGES: List[Tuple[str, str, re.Pattern]] = [
    ("piling", "Piling", re.compile(r"^piling - mms", re.I)),
    ("capping", "Pile capping", re.compile(r"^pile capping", re.I)),
    ("torque_tube", "Torque tube / rafter", re.compile(r"^mms erection - torque tube", re.I)),
    ("bracing", "Shaft / bracing", re.compile(r"^mms erection - transmission shaft", re.I)),
    ("purlin", "Purlin (structure ready)", re.compile(r"^mms erection - purlin", re.I)),
    ("module", "Module installation", re.compile(r"^module installation\s*$", re.I)),
]
STAGE_KEYS = [k for k, _, _ in STAGES]
STAGE_LABELS = {k: lbl for k, lbl, _ in STAGES}
BLOCK_FTC = re.compile(r"first time charging", re.I)
_BLOCK = re.compile(r"^\s*block[- ]?(\d+[a-z]?)\s*-\s*(.+?)\s*$", re.I)

LATEST_P6 = """
    SELECT DISTINCT ON (project_id) project_id, p6_object_id, data_date, current_baseline_project_object_id
    FROM p6_project
    WHERE project_id IS NOT NULL AND project_id NOT ILIKE '%%\\_old'
    ORDER BY project_id, data_date DESC NULLS LAST, last_synced_at DESC NULLS LAST, p6_object_id DESC
"""


def _d(x) -> Optional[date]:
    if x is None:
        return None
    return x.date() if isinstance(x, datetime) else x


def _iso(x) -> Optional[str]:
    x = _d(x)
    return x.isoformat() if x else None


# ── Loading ─────────────────────────────────────────────────────────────────
def _load(db: Session, project_ids: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """Every block's stage activities and FTC milestone, plus each project's
    phase FTC milestones and assigned baseline, from the latest schedule."""
    where = "AND l.project_id = ANY(:pids)" if project_ids else ""
    params = {"pids": project_ids} if project_ids else {}
    rows = db.execute(text(f"""
        WITH l AS ({LATEST_P6})
        SELECT l.project_id, l.data_date, a.name, a.status, a.percent_complete,
               a.actual_start_date, a.actual_finish_date,
               a.planned_start_date, a.planned_finish_date,
               a.baseline_start_date, a.baseline_finish_date,
               SUM(r.planned_units) FILTER (WHERE r.resource_name ILIKE '%%construction%%'),
               SUM(r.actual_units) FILTER (WHERE r.resource_name ILIKE '%%construction%%')
        FROM l
        JOIN p6_activity a ON a.project_object_id = l.p6_object_id
        LEFT JOIN p6_resource_assignment r
               ON r.activity_object_id = a.p6_object_id AND r.resource_type = 'Material'
        WHERE a.name ~* '^\\s*block[- ]?\\d+' {where}
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11"""), params).fetchall()

    out: Dict[str, Dict[str, Any]] = {}
    for (pid, data_date, name, status, pct, a_s, a_f, p_s, p_f, b_s, b_f, q_plan, q_act) in rows:
        m = _BLOCK.match(name or "")
        if not m:
            continue
        rest = re.sub(r"\s+", " ", m.group(2))
        proj = out.setdefault(pid, {"data_date": _d(data_date), "blocks": defaultdict(dict)})
        block = m.group(1).upper().lstrip("0") or "0"
        if BLOCK_FTC.search(rest):
            proj["blocks"][block]["_ftc"] = {"planned": _d(p_f), "actual": _d(a_f), "baseline": _d(b_f)}
            continue
        key = next((k for k, _, pat in STAGES if pat.match(rest)), None)
        if not key:
            continue
        proj["blocks"][block][key] = {
            "status": status, "pct": float(pct or 0),
            "actual_start": _d(a_s), "actual_finish": _d(a_f),
            "planned_start": _d(p_s), "planned_finish": _d(p_f),
            "baseline_start": _d(b_s), "baseline_finish": _d(b_f),
            "qty_planned": float(q_plan or 0), "qty_actual": float(q_act or 0),
        }

    if not out:
        return out
    # Phase FTC milestones - the same selection as the Ordering Schedule
    # (routers.module_deliveries 5d): project/phase Finish Milestones under
    # the Milestones WBS, not the per-block ones.
    for pid, name, p_f, a_f in db.execute(text(f"""
            WITH l AS ({LATEST_P6})
            SELECT l.project_id, a.name, a.planned_finish_date, a.actual_finish_date
            FROM l JOIN p6_activity a ON a.project_object_id = l.p6_object_id
            WHERE (a.name ILIKE '%%First Time Charging%%' OR a.name ILIKE '%%FTC%%')
              AND a.type = 'Finish Milestone'
              AND (a.wbs_name ILIKE '%%MILESTONE%%' OR a.wbs_name ILIKE 'PHASE-%%')
              AND a.name !~* '^\\s*block' AND a.name !~* 'switchyard'
              AND l.project_id = ANY(:pids)
            ORDER BY COALESCE(a.actual_finish_date, a.planned_finish_date), a.p6_object_id"""),
            {"pids": list(out)}):
        if pid in out:
            out[pid].setdefault("phases", []).append(
                {"name": name, "date": _d(a_f) or _d(p_f), "charged": a_f is not None})
    for pid, bl_name in db.execute(text(f"""
            WITH l AS ({LATEST_P6})
            SELECT l.project_id, b.name FROM l
            LEFT JOIN p6_baseline_project b ON b.p6_object_id = l.current_baseline_project_object_id
            WHERE l.project_id = ANY(:pids)"""), {"pids": list(out)}):
        if pid in out:
            out[pid]["baseline"] = bl_name
    return out


# ── Measured behaviour per project ──────────────────────────────────────────
def _frac(a: Dict[str, Any]) -> float:
    if a["actual_finish"]:
        return 1.0
    if a["qty_planned"] > 0:
        return max(0.0, min(1.0, a["qty_actual"] / a["qty_planned"]))
    return max(0.0, min(1.0, a["pct"] if a["pct"] <= 1 else a["pct"] / 100))


def _span(start: Optional[date], finish: Optional[date]) -> Optional[int]:
    return (finish - start).days + 1 if start and finish and finish >= start else None


def _stats(blocks: Dict[str, Dict[str, Any]], as_of: date, has_baseline: bool) -> Dict[str, Dict[str, Any]]:
    """Per stage, from this project's own completed blocks: how long a stage
    actually takes against its baseline duration (the duration factor), the
    start gap after the previous stage, and blocks finished in the last 30
    days.  Measured 2026-10-11 over 213-369 completed blocks: piling 1.06x
    baseline, capping 1.2x, torque tube / bracing / purlin ~1.9x, modules
    1.35x."""
    out: Dict[str, Dict[str, Any]] = {}
    for i, k in enumerate(STAGE_KEYS):
        ratios, lags, recent, own_durs = [], [], 0, []
        prev = STAGE_KEYS[i - 1] if i else None
        for b in blocks.values():
            a = b.get(k)
            if not a:
                continue
            if a["actual_finish"] and (as_of - a["actual_finish"]).days <= RECENT_DAYS:
                recent += 1
            act, base = _span(a["actual_start"], a["actual_finish"]), _span(a["baseline_start"], a["baseline_finish"])
            if act:
                own_durs.append(act)
            if has_baseline and act and base:
                ratios.append(act / base)
            p = b.get(prev) if prev else None
            if p and p["actual_start"] and a["actual_start"]:
                lags.append((a["actual_start"] - p["actual_start"]).days)
        if k == "module":
            ftc_lags = [(b["_ftc"]["actual"] - b["module"]["actual_finish"]).days
                        for b in blocks.values()
                        if b.get("module") and b["module"]["actual_finish"]
                        and (b.get("_ftc") or {}).get("actual")]
        out[k] = {
            "factor": median(ratios) if len(ratios) >= MIN_SAMPLES else None,
            "factor_n": len(ratios),
            "lag": median(lags) if len(lags) >= MIN_SAMPLES else None,
            "lag_n": len(lags),
            "own_duration": median(own_durs) if len(own_durs) >= MIN_SAMPLES else None,
            "own_n": len(own_durs),
            "done_last_30d": recent,
        }
    out["_ftc_lag"] = median(ftc_lags) if len(ftc_lags) >= MIN_SAMPLES else None
    return out


def _portfolio_stats(all_stats: List[Dict[str, Dict[str, Any]]],
                     data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Fallbacks for a project with fewer than 3 completed blocks: the median
    over the projects that have their own figure.  `typical_base` is the
    usual baseline duration of the stage on one block (~26-35 d)."""
    lags_ftc = [s["_ftc_lag"] for s in all_stats if s.get("_ftc_lag") is not None]
    out = {"_ftc_lag": median(lags_ftc) if lags_ftc else None}
    for k in STAGE_KEYS:
        fs = [s[k]["factor"] for s in all_stats if s[k]["factor"] is not None]
        lags = [s[k]["lag"] for s in all_stats if s[k]["lag"] is not None]
        spans = [sp for p in data.values() for b in p["blocks"].values() if k in b
                 and (sp := _span(b[k]["baseline_start"], b[k]["baseline_finish"]))]
        out[k] = {"factor": median(fs) if fs else 1.0, "lag": median(lags) if lags else None,
                  "typical_base": median(spans) if spans else None}
    return out


FACTOR_RANGE = (0.5, 4.0)       # one odd project cannot stretch a forecast past this
# Duration source per stage, chosen by backtest on 1,764 finished block-stages
# (scripts/backtest_advanced_planning.py, 2026-10-11): the structure stages
# are best forecast from this project's own finished blocks (median error
# 23-29 d vs 28-30 d from the baseline); piling, capping and modules from the
# P6 plan (13-25 d). "Baseline x slowness factor" lost on every stage.
OWN_HISTORY_STAGES = {"torque_tube", "bracing", "purlin"}


# ── Forecast per block ──────────────────────────────────────────────────────
def _weather_days(start: date, work_days: float, wx) -> int:
    """Extra calendar days the season adds to `work_days` of normal-pace work
    starting on `start` (negative in a dry stretch). wx(day) is the site's
    seasonal speed factor, 1.0 = an average day."""
    if wx is None or work_days <= 0:
        return 0
    d, done, steps = start, 0.0, 0
    while done < work_days and steps < 3 * FORECAST_CAP_DAYS:
        done += wx(d)
        d += timedelta(days=1)
        steps += 1
    return steps - int(-(-work_days // 1))      # vs the same work at 1.0 a day


def _forecast_block(b: Dict[str, Any], st: Dict[str, Dict[str, Any]],
                    pf: Dict[str, Dict[str, Any]], as_of: date, has_baseline: bool,
                    wx=None) -> Dict[str, Any]:
    stages, prev_start, prev_finish, prev_finish_wx = [], None, None, None
    for i, k in enumerate(STAGE_KEYS):
        a = b.get(k)
        if not a:
            stages.append({"key": k, "label": STAGE_LABELS[k], "missing": True})
            continue
        f = _frac(a)
        # Duration: the block's own planned duration (assigned baseline, else
        # current P6 plan) x how much longer this stage really takes here.
        base = (_span(a["baseline_start"], a["baseline_finish"]) if has_baseline else None) \
            or _span(a["planned_start"], a["planned_finish"]) or 30
        factor = st[k]["factor"] if st[k]["factor"] is not None else pf[k]["factor"]
        factor = min(FACTOR_RANGE[1], max(FACTOR_RANGE[0], factor))
        own = st[k].get("own_duration")
        if k in OWN_HISTORY_STAGES and own:
            dur, basis = own, f"{own:.0f} d, as this project's finished blocks took (median of {st[k]['own_n']})"
        else:
            dur, basis = base, f"{base} d, as planned in P6"
        wdays = 0
        if a["actual_finish"]:
            start, finish, how = a["actual_start"] or a["actual_finish"], a["actual_finish"], "actual"
        elif a["actual_start"]:
            start = a["actual_start"]
            elapsed = max(1, (as_of - start).days)
            # What this stage normally takes on one block. Not the block's own
            # baseline span: a block already running at a re-baseline keeps
            # its old actual start, so its "plan" can be a year (BAIYA 44).
            # Judged against the stage's usual length across all projects: a
            # project's own history can itself be stretched by stalls (FY26-P08
            # capping, 44% in 269 d, read as "normal" against its own median).
            usual = (pf[k].get("typical_base") or base) * factor
            if f >= OWN_PACE_MIN_FRAC and elapsed <= PAUSED_FACTOR * usual:
                rem = elapsed * (1 - f) / f
                how = f"own pace so far ({f * 100:.0f}% in {elapsed} d)"
            elif elapsed > PAUSED_FACTOR * usual:
                # Open far longer than the stage takes: the block was paused
                # (FY26-P05 block 9, piling 34% in 238 d). Crawling at that
                # average would put it in 2028; the rest goes at the usual pace.
                rem = max(1.0, usual * (1 - f))
                how = (f"slow or paused ({f * 100:.0f}% in {elapsed} d); rest at the usual "
                       f"{usual:.0f} d per block")
            else:
                rem = max(1.0, dur * (1 - f))
                how = f"remaining of {basis}"
            rem = min(FORECAST_CAP_DAYS, rem)
            finish = as_of + timedelta(days=round(rem))
            wdays = _weather_days(as_of, rem, wx)
        else:
            # Start: the gap after the previous stage this project's blocks
            # show, else the block's own baseline gap, else other projects'.
            lag = st[k]["lag"]
            if lag is None and i and has_baseline:
                p = b.get(STAGE_KEYS[i - 1])
                if p and p["baseline_start"] and a["baseline_start"]:
                    lag = (a["baseline_start"] - p["baseline_start"]).days
            if lag is None:
                lag = pf[k]["lag"]
            cands = [as_of]
            if prev_start is not None and lag is not None:
                cands.append(prev_start + timedelta(days=round(max(0, lag))))
            elif a["planned_start"]:
                cands.append(a["planned_start"])
            start = max(cands)
            finish = start + timedelta(days=max(1, round(dur)) - 1)
            wdays = _weather_days(start, dur, wx)
            how = f"after previous stage; {basis}"
        # Stages overlap (start-to-start gaps: bracing starts with torque
        # tube, modules ~40 d into purlin), but none can finish before the
        # work it sits on: modules cannot be done before the purlins are.
        finish_wx = finish + timedelta(days=wdays)
        if not a["actual_finish"] and prev_finish is not None and finish < prev_finish:
            finish = prev_finish
            how += "; held to finish after the previous stage"
        if not a["actual_finish"] and prev_finish_wx is not None and finish_wx < prev_finish_wx:
            finish_wx = prev_finish_wx
        delay = None
        if has_baseline and a["baseline_finish"]:
            delay = (finish - a["baseline_finish"]).days
        stages.append({
            "key": k, "label": STAGE_LABELS[k], "pct": round(f * 100, 1),
            "done": bool(a["actual_finish"]), "started": bool(a["actual_start"]),
            "forecast_start": _iso(start), "forecast_finish": _iso(finish), "basis": how,
            # With the season's weather: the extra (or saved) days on top.
            "forecast_finish_wx": _iso(finish_wx) if wx else None,
            "weather_days": (finish_wx - finish).days if wx else None,
            "baseline_finish": _iso(a["baseline_finish"]) if has_baseline else None,
            "delay_days": delay,
            "duration_days": round(dur),
            "qty_planned": round(a["qty_planned"], 1), "qty_actual": round(a["qty_actual"], 1),
        })
        prev_start, prev_finish, prev_finish_wx = start, finish, finish_wx
    return {"stages": stages}


def _block_no(blk: str) -> int:
    m = re.match(r"(\d+)", blk)
    return int(m.group(1)) if m else 0


def _phase_ranges(name: str) -> Optional[set]:
    """Blocks a phase names itself ("... BL- 34, 36 to 41, 44"), or None."""
    m = re.search(r"\bBL[\s\-]*[:\-]?\s*(\d.*)$", name or "", re.I)
    if not m:
        return None
    out: set = set()
    for part in re.split(r"[,&]", m.group(1)):
        nums = [int(n) for n in re.findall(r"\d+", part)]
        if re.search(r"\bto\b", part, re.I) and len(nums) >= 2:
            out.update(range(nums[0], nums[1] + 1))
        elif nums:
            out.add(nums[0])
    return out or None


def _assign_phases(blocks: Dict[str, Dict[str, Any]], phases: List[Dict[str, Any]]) -> Tuple[Dict[str, int], str]:
    """Block -> FTC phase index, and how it was decided. In order of how
    explicit P6 is:
      1. block ranges in the phase names ("BL- 01 to 14", FY27-P16-3-2);
      2. block counts in the names ("5 Blocks/ 59 MW", BAIYA) and otherwise
         each phase's MW share - blocks taken in the order they charge (their
         own FTC milestone, then block number) and filled phase by phase;
      3. the first phase FTC on or after the block's own FTC date.
    Checked 2026-10-11: rule 2 reproduces BAIYA's 21/5/7/8/11 exactly; the
    date rule alone left 100-125 MW phases empty on FY26-P05 and FY26-P23."""
    if not phases:
        return {}, "no FTC milestone"
    if len(phases) == 1:
        return {blk: 0 for blk in blocks}, "single FTC"
    out: Dict[str, int] = {}
    ranges = [_phase_ranges(p["name"]) for p in phases]
    if any(ranges):
        for blk in blocks:
            hit = next((i for i, r in enumerate(ranges) if r and _block_no(blk) in r), None)
            if hit is not None:
                out[blk] = hit
        free = [i for i, r in enumerate(ranges) if not r]
        for blk in blocks:
            if blk not in out:
                out[blk] = free[0] if len(free) == 1 else (free or [len(phases) - 1])[-1]
        return out, "block ranges in the FTC milestone names"

    def own_date(b):
        f = b.get("_ftc") or {}
        return f.get("actual") or f.get("planned") or date.max

    order = sorted(blocks, key=lambda blk: (own_date(blocks[blk]), _block_no(blk)))
    n = len(order)
    counts = [int(m.group(1)) if (m := re.search(r"(\d+)\s*Blocks?\b", p["name"], re.I)) else None
              for p in phases]
    mws = [float(m.group(1)) if (m := re.search(r"(\d+(?:\.\d+)?)\s*MW", p["name"], re.I)) else None
           for p in phases]
    fixed = sum(c for c in counts if c)
    open_idx = [i for i, c in enumerate(counts) if c is None]
    if fixed <= n and (not open_idx or all(mws[i] for i in open_idx)):
        rest = n - fixed
        share_total = sum(mws[i] for i in open_idx) or 1
        alloc = {i: c for i, c in enumerate(counts) if c is not None}
        raw = {i: rest * mws[i] / share_total for i in open_idx}
        floor = {i: int(v) for i, v in raw.items()}
        spare = rest - sum(floor.values())
        for i in sorted(raw, key=lambda i: raw[i] - floor[i], reverse=True)[:spare]:
            floor[i] += 1
        alloc.update(floor)
        pos = 0
        for i in range(len(phases)):
            for blk in order[pos:pos + alloc.get(i, 0)]:
                out[blk] = i
            pos += alloc.get(i, 0)
        for blk in order[pos:]:
            out[blk] = len(phases) - 1
        return out, ("block counts and MW in the FTC milestone names" if fixed
                     else "MW in the FTC milestone names, blocks in charging order")

    dated = [(i, p["date"]) for i, p in enumerate(phases) if p["date"]]
    for blk, b in blocks.items():
        d = own_date(b)
        out[blk] = next((i for i, pd in dated if pd >= d), dated[-1][0]) if dated else len(phases) - 1
    return out, "each block's own FTC date"


# ── Plan ────────────────────────────────────────────────────────────────────
def _lead_days(source: Optional[str]) -> int:
    return LEAD_TIMES.get((source or "").strip(), DEFAULT_LEAD_TIME)


def build(db: Session, supply_rows: List[Dict[str, Any]], as_of: Optional[date] = None) -> Dict[str, Any]:
    """`supply_rows`: the Ordering Schedule's project rows (id, project_name,
    ordered_mwp, total_receipt_mwp, erection_done_mwp, under_transit_mwp,
    type = origin, ol), each with its P6 project_id added by the caller."""
    as_of = as_of or date.today()
    by_pid: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in supply_rows:
        if r.get("project_id"):
            by_pid[r["project_id"]].append(r)
    data = _load(db, list(by_pid))
    stats = {pid: _stats(p["blocks"], as_of, bool(p.get("baseline"))) for pid, p in data.items()}
    pf = _portfolio_stats(list(stats.values()), data)

    projects = []
    for pid, rows in by_pid.items():
        p = data.get(pid)
        head = {
            "project_id": pid, "ids": [r["id"] for r in rows],
            "project_name": rows[0].get("project_name") or pid,
            "p6_name": rows[0].get("p6_name"),
            "origin": rows[0].get("type"), "priority": rows[0].get("priority"),
        }
        if not p or not any(any(k in b for k in STAGE_KEYS) for b in p["blocks"].values()):
            projects.append({**head, "plannable": False,
                             "reason": "No block activities in the P6 schedule."})
            continue
        weather = site_weather.site_factor(pid, as_of)
        projects.append({**head, **_plan_project(p, rows, stats[pid], pf, as_of, weather)})

    quota = _level_vendor_quota(projects, by_pid, as_of)

    # AI first, the measured engine as the fallback (services/ai_prediction.py).
    asks = {}
    for pr in projects:
        if pr.get("plannable"):
            req = ai_prediction.request_for(pr, by_pid[pr["project_id"]])
            if req:
                asks[pr["project_id"]] = req
    ai, ai_status = ai_prediction.predict(asks)
    for pr in projects:
        if pr.get("plannable"):
            pr["ai"] = ai.get(pr["project_id"])
            pr["decision"] = _decide(pr, ai_status if pr["project_id"] in asks
                                     else "no open FTC for the AI to forecast")

    projects.sort(key=lambda x: (not x.get("plannable", True),
                                 x.get("first_order_by") or "9999", x["project_name"]))
    months: Dict[str, float] = defaultdict(float)
    for pr in projects:
        for m, v in (pr.get("order_months") or {}).items():
            months[m] += v
    return {
        "as_of": as_of.isoformat(), "buffer_days": SITE_BUFFER_DAYS,
        "projects": projects,
        "order_months": {m: round(v, 1) for m, v in sorted(months.items())},
        "ai_status": ai_status,
        "quota": quota,
        "basis": ("Stage progress and dates: P6 block activities, updated daily. Delay: forecast vs the "
                  "project's assigned P6 baseline. Forecast (estimate): a running stage at its own pace; "
                  "a stage not started begins the measured gap after the previous one starts (stages "
                  "overlap) and takes its planned duration x how much longer that stage really takes on "
                  "this project; no stage finishes before the one it sits on. Modules needed 14 days "
                  "before forecast module installation start. Supply: Ordering Schedule figures (SAP / Ariba)."),
    }


def _plan_project(p: Dict[str, Any], rows: List[Dict[str, Any]],
                  st: Dict[str, Dict[str, Any]], pf: Dict[str, Dict[str, Any]], as_of: date,
                  weather: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    blocks = {k: v for k, v in p["blocks"].items() if any(s in v for s in STAGE_KEYS)}
    has_baseline = bool(p.get("baseline"))
    phases = p.get("phases") or []
    phase_of, phase_basis = _assign_phases(blocks, phases)
    origin = rows[0].get("type")
    lead = _lead_days(origin)

    # Supply, project level, as the Ordering Schedule reports it.
    ordered = sum(r.get("ordered_mwp") or 0 for r in rows)
    received = sum(r.get("total_receipt_mwp") or 0 for r in rows)
    erected = sum(r.get("erection_done_mwp") or 0 for r in rows)
    in_transit = sum(r.get("under_transit_mwp") or 0 for r in rows)
    stock = max(0.0, received - erected)
    on_order = max(0.0, ordered - received - in_transit)
    available = stock + in_transit + on_order

    wx = weather["factor"] if weather else None
    # Modules done -> block charged: this project's finished blocks, else all
    # projects', else the block's own plan.
    ftc_lag = st.get("_ftc_lag") if st.get("_ftc_lag") is not None else pf.get("_ftc_lag")

    plans = []
    for blk, b in blocks.items():
        fc = _forecast_block(b, st, pf, as_of, has_baseline, wx)
        mod = b.get("module")
        mwp = (mod or {}).get("qty_planned") or 0.0
        installed = (mod or {}).get("qty_actual") or 0.0
        if mod and mod["actual_finish"]:
            installed = mwp
        mstage = next(s for s in fc["stages"] if s["key"] == "module")
        need_start = _d(datetime.fromisoformat(mstage["forecast_start"])) if mstage.get("forecast_start") else None
        need_by = need_start - timedelta(days=SITE_BUFFER_DAYS) if need_start else None
        if mod and mod["actual_start"] and need_by is not None:
            need_by = max(need_by, as_of)        # installing now: the rest is needed now
        ftc = b.get("_ftc") or {}
        parts = None
        if not ftc.get("actual") and mstage.get("forecast_finish"):
            lag = ftc_lag
            if lag is None and ftc.get("planned") and mod and mod.get("planned_finish"):
                lag = (ftc["planned"] - mod["planned_finish"]).days
            # Install time still to go on this block, at its forecast duration.
            dur_m = mstage.get("duration_days") or 0
            parts = {"site_done": mstage["forecast_finish"], "site_done_wx": mstage.get("forecast_finish_wx"),
                     "install_days": max(1, round(dur_m * (1 - (mstage.get("pct") or 0) / 100))),
                     "charge_gap_days": max(0, round(lag if lag is not None else 0))}
        plans.append({
            "block": blk, "phase": phase_of.get(blk), "mwp": round(mwp, 2),
            "installed_mwp": round(installed, 2), "remaining_mwp": round(max(0.0, mwp - installed), 2),
            "stages": fc["stages"], "need_by": _iso(need_by),
            "ftc_planned": _iso(ftc.get("planned")), "ftc_actual": _iso(ftc.get("actual")),
            "ftc_baseline": _iso(ftc.get("baseline")) if has_baseline else None,
            "ftc_forecast": _iso(ftc.get("actual")), "ftc_forecast_wx": _iso(ftc.get("actual")) if wx else None,
            "ftc_parts": parts,
        })
        _block_ftc(plans[-1], as_of, bool(wx))

    def _blk_key(x):
        m = re.match(r"(\d+)", x["block"])
        return (int(m.group(1)) if m else 0, x["block"])

    # Net supply against need, earliest need first.
    left = available
    order_months: Dict[str, float] = defaultdict(float)
    for pl in sorted(plans, key=lambda x: (x["need_by"] or "9999", _blk_key(x))):
        rem = pl["remaining_mwp"]
        if rem <= 0.01:
            pl.update(status="installed", covered_mwp=0.0, short_mwp=0.0, order_by=None)
            continue
        cover = min(left, rem)
        left -= cover
        short = rem - cover
        pl["covered_mwp"], pl["short_mwp"] = round(cover, 2), round(short, 2)
        if short <= max(SHORT_TOLERANCE_MWP, 0.02 * rem):
            pl.update(status="covered", order_by=None, short_mwp=0.0)
            continue
        need = date.fromisoformat(pl["need_by"]) if pl["need_by"] else None
        if need is None:
            pl.update(status="no_dates", order_by=None)
            continue
        order_by = need - timedelta(days=lead)
        pl["order_by"] = order_by.isoformat()
        if order_by < as_of:
            pl["status"] = "late"
        elif (order_by - as_of).days <= 30:
            pl["status"] = "order_now"
        else:
            pl["status"] = "hold"
        month = max(order_by, as_of).strftime("%Y-%m")
        order_months[month] += short
        arrival = max(need, as_of + timedelta(days=lead))
        pl["arrival"] = arrival.isoformat()
        pl["arrival_late_days"] = max(0, (arrival - need).days)
        _block_ftc(pl, as_of, bool(wx))
        pl["reason"] = _reason(pl, lead, origin)

    # Phases: FTC at risk when a block's modules finish after the phase FTC.
    phase_out = []
    for i, ph in enumerate(phases):
        mine = [pl for pl in plans if pl["phase"] == i]
        late = []
        for pl in mine:
            mfin = next((s.get("forecast_finish") for s in pl["stages"] if s["key"] == "module"), None)
            if ph["date"] and mfin and not ph["charged"] and mfin > ph["date"].isoformat():
                late.append({"block": pl["block"], "modules_done": mfin,
                             "holding_stage": _holding_stage(pl)})
        fc_finish = max((s.get("forecast_finish") for pl in mine for s in pl["stages"]
                         if s["key"] == "module" and s.get("forecast_finish")), default=None)
        ftc_fc = max((pl["ftc_forecast"] for pl in mine if pl.get("ftc_forecast")), default=None)
        ftc_fc_wx = max((pl["ftc_forecast_wx"] for pl in mine if pl.get("ftc_forecast_wx")), default=None)
        phase_out.append({
            "ftc_forecast": ftc_fc if not ph["charged"] else _iso(ph["date"]),
            "ftc_forecast_wx": (ftc_fc_wx if not ph["charged"] else _iso(ph["date"])) if wx else None,
            "slip_days": ((date.fromisoformat(ftc_fc) - ph["date"]).days
                          if ftc_fc and ph["date"] and not ph["charged"] else None),
            "index": i, "name": ph["name"], "ftc": _iso(ph["date"]), "charged": ph["charged"],
            "blocks": sorted((pl["block"] for pl in mine), key=lambda b: _blk_key({"block": b})),
            "mwp": round(sum(pl["mwp"] for pl in mine), 1),
            "modules_complete_forecast": fc_finish,
            "at_risk": bool(late), "late_blocks": sorted(late, key=lambda x: x["modules_done"], reverse=True),
        })

    stage_summary = []
    for k in STAGE_KEYS:
        inst = [b[k] for b in blocks.values() if k in b]
        if not inst:
            continue
        done = sum(1 for a in inst if a["actual_finish"])
        qp = sum(a["qty_planned"] for a in inst)
        qa = sum(a["qty_actual"] if not a["actual_finish"] else a["qty_planned"] for a in inst)
        delays = [s["delay_days"] for pl in plans for s in pl["stages"]
                  if s["key"] == k and s.get("delay_days") is not None and not s.get("done")]
        stage_summary.append({
            "key": k, "label": STAGE_LABELS[k], "blocks": len(inst), "blocks_done": done,
            "pct": round(qa / qp * 100, 1) if qp > 0 else round(done / len(inst) * 100, 1),
            "done_last_30d": st[k]["done_last_30d"],
            "duration_factor": round(st[k]["factor"] if st[k]["factor"] is not None else pf[k]["factor"], 2),
            "factor_basis": (f"this project ({st[k]['factor_n']} blocks)" if st[k]["factor"] is not None
                             else "all projects"),
            "worst_delay_days": max(delays) if delays else None,
            "forecast_finish": max((s["forecast_finish"] for pl in plans for s in pl["stages"]
                                    if s["key"] == k and s.get("forecast_finish")), default=None),
        })

    short_blocks = [pl for pl in plans if pl.get("order_by")]
    plans.sort(key=_blk_key)
    return {
        "plannable": True, "data_date": _iso(p["data_date"]),
        "baseline": p.get("baseline"), "has_baseline": has_baseline,
        "lead_days": lead,
        "supply": {"ordered_mwp": round(ordered, 1), "received_mwp": round(received, 1),
                   "erected_mwp": round(erected, 1), "stock_mwp": round(stock, 1),
                   "in_transit_mwp": round(in_transit, 1), "on_order_mwp": round(on_order, 1),
                   "available_mwp": round(available, 1),
                   "need_mwp": round(sum(pl["remaining_mwp"] for pl in plans), 1),
                   "short_mwp": round(sum(pl.get("short_mwp") or 0 for pl in plans), 1)},
        "stages": stage_summary, "phases": phase_out, "blocks": plans,
        "first_order_by": min((pl["order_by"] for pl in short_blocks), default=None),
        "no_po": ordered <= 0.01,
        # Last FTC of the project, forecast - what LTA / SCOD are judged against.
        "completion_forecast": max((ph["ftc_forecast"] for ph in phase_out if ph.get("ftc_forecast")),
                                   default=max((pl["ftc_forecast"] for pl in plans if pl.get("ftc_forecast")), default=None)),
        "completion_forecast_wx": (max((ph["ftc_forecast_wx"] for ph in phase_out if ph.get("ftc_forecast_wx")),
                                       default=max((pl["ftc_forecast_wx"] for pl in plans if pl.get("ftc_forecast_wx")), default=None))
                                   if wx else None),
        "weather": ({k: v for k, v in weather.items() if k != "factor"} if weather
                    else {"station": None, "source": "Location not known - add the project's pooling substation"}),
        "phase_basis": phase_basis,
        "order_months": {m: round(v, 1) for m, v in sorted(order_months.items())},
        "status": ("late" if any(pl["status"] == "late" for pl in plans)
                   else "order_now" if any(pl["status"] == "order_now" for pl in plans)
                   else "hold" if short_blocks else "covered"),
    }


# ── Vendor monthly limits ───────────────────────────────────────────────────
LEVEL_HORIZON = 24          # months; past it an order is shown in the last month, over the limit


def _quota_key(origin: Optional[str]) -> str:
    o = (origin or "").strip().lower()
    # An origin the register does not name gets the default limit, labelled so.
    return {"china": "China", "sea": "SEA", "almm": "ALMM", "alcm": "ALCM", "dcr": "DCR", "india": "ALMM"}.get(o, "Origin not set")


def _month_start(d: date, add: int = 0) -> date:
    n = d.month - 1 + add
    return date(d.year + n // 12, n % 12 + 1, 1)


def _level_vendor_quota(projects: List[Dict[str, Any]], by_pid: Dict[str, List[Dict[str, Any]]],
                        as_of: date) -> Dict[str, Any]:
    """Fit every short block's order into its origin's monthly limit (MWac,
    services.module_planner.CAP_LIMITS), the same rules as the standard plan:

      who first   PPA projects, then P1 / P2 / standard, then the earliest
                  FTC, then the earliest need date;
      where       the block's own order month (the correct timing); if that
                  month is full, the nearest earlier month (early costs yard
                  space, not FTC); only when every earlier month is full, a
                  later month - a real delay, carried through to the block's
                  arrival and FTC.

    Each block gets `allocations` (month -> MWp), `order_by_leveled` and
    `quota` = on_time | early | delayed."""
    m0 = _month_start(as_of)
    months = [_month_start(m0, i) for i in range(LEVEL_HORIZON)]

    def idx(d: date) -> int:
        return max(0, min(LEVEL_HORIZON - 1, (d.year - m0.year) * 12 + d.month - m0.month))

    lots = []
    for pr in projects:
        if not pr.get("plannable"):
            continue
        rows = by_pid[pr["project_id"]]
        ol = float(rows[0].get("ol") or 0) or 1.35
        src = _quota_key(pr.get("origin"))
        is_ppa = any((r.get("category") == "PPA") or "PPA" in (r.get("project_name") or "").upper()
                     or "PPA" in (r.get("p6_name") or "").upper() for r in rows)
        rank = PRIORITY_RANKS.get(rows[0].get("priority") or "standard", 3)
        pr["quota_source"] = src
        for b in pr.get("blocks") or []:
            if not b.get("order_by") or not b.get("short_mwp"):
                continue
            ob = date.fromisoformat(b["order_by"])
            lots.append({"pr": pr, "b": b, "src": src, "ol": ol, "mwac": b["short_mwp"] / ol, "ob": ob,
                         "target": idx(max(ob, as_of)), "lead": pr.get("lead_days") or DEFAULT_LEAD_TIME,
                         "key": (0 if is_ppa else 1, rank, b.get("ftc_planned") or "9999",
                                 b.get("need_by") or "9999", pr["project_id"], b["block"])})

    used: Dict[tuple, float] = defaultdict(float)
    for lot in sorted(lots, key=lambda l: l["key"]):
        src, t, b = lot["src"], lot["target"], lot["b"]
        cap = CAP_LIMITS.get(src, DEFAULT_CAP)
        rem, allocs = lot["mwac"], []
        for i in [t] + list(range(t - 1, -1, -1)) + list(range(t + 1, LEVEL_HORIZON)):
            room = cap - used[(src, i)]
            if room <= 1e-6:
                continue
            take = min(rem, room)
            used[(src, i)] += take
            allocs.append((i, take))
            rem -= take
            if rem <= 1e-6:
                break
        if rem > 1e-6:          # past the horizon: last month, over the limit
            used[(src, LEVEL_HORIZON - 1)] += rem
            allocs.append((LEVEL_HORIZON - 1, rem))
        allocs.sort()
        b["allocations"] = [{"month": months[i].strftime("%Y-%m"), "mwp": round(v * lot["ol"], 2),
                             "mwac": round(v, 2)} for i, v in allocs]
        first, last = allocs[0][0], allocs[-1][0]
        correct = max(lot["ob"], as_of)
        if first < t:
            # Ordered in an earlier month: as late in it as possible.
            placed = min(correct, _month_start(months[first], 1) - timedelta(days=1))
            b["quota"] = "early"
        elif last > t:
            placed = max(correct, months[last])
            b["quota"] = "delayed"
        else:
            placed, b["quota"] = correct, "on_time"
        b["order_by_leveled"] = placed.isoformat()
        b["quota_shift_days"] = (placed - correct).days
        b["quota_reason"] = (f"{src} limit {cap:.0f} MWac/month full in {months[t].strftime('%b-%y')}"
                             if b["quota"] != "on_time" else None)
        if b["quota"] == "delayed":
            # Ordered later than needed: modules land later, and so the FTC.
            need = date.fromisoformat(b["need_by"])
            arrival = max(need, max(as_of, placed) + timedelta(days=lot["lead"]))
            old = date.fromisoformat(b["arrival"]) if b.get("arrival") else need
            if arrival > old:
                b["arrival"] = arrival.isoformat()
                b["arrival_late_days"] = max(0, (arrival - need).days)
                _block_ftc(b, as_of, b.get("ftc_forecast_wx") is not None)

    # Roll the levelled orders back up per project.
    for pr in projects:
        if not pr.get("plannable"):
            continue
        om: Dict[str, float] = defaultdict(float)
        for b in pr.get("blocks") or []:
            for a in b.get("allocations") or []:
                om[a["month"]] += a["mwp"]
        pr["order_months"] = {m: round(v, 1) for m, v in sorted(om.items())}
        leveled = [b["order_by_leveled"] for b in pr.get("blocks") or [] if b.get("order_by_leveled")]
        pr["first_order_by"] = min(leveled) if leveled else pr.get("first_order_by")
        pr["quota_flags"] = {f: sum(1 for b in pr.get("blocks") or [] if b.get("quota") == f)
                             for f in ("early", "delayed")}
        _refresh_ftc(pr)

    return {
        "limits_mwac": {**CAP_LIMITS, "Origin not set": DEFAULT_CAP},
        "used_mwac": {src: {months[i].strftime("%Y-%m"): round(v, 1) for (s_, i), v in sorted(used.items()) if s_ == src}
                      for src in sorted({k[0] for k in used})},
        "months": [m.strftime("%Y-%m") for m in months],
        "rule": "PPA first, then P1 / P2 / standard, then earliest FTC; target month, else earlier, else later.",
    }


def _refresh_ftc(pr: Dict[str, Any]) -> None:
    """Phase and project FTC forecasts after supply moved some blocks."""
    blocks = pr.get("blocks") or []
    for ph in pr.get("phases") or []:
        if ph.get("charged"):
            continue
        mine = [b for b in blocks if b.get("phase") == ph["index"]]
        fc = max((b["ftc_forecast"] for b in mine if b.get("ftc_forecast")), default=None)
        fcw = max((b["ftc_forecast_wx"] for b in mine if b.get("ftc_forecast_wx")), default=None)
        if fc:
            ph["ftc_forecast"] = fc
            ph["slip_days"] = (date.fromisoformat(fc) - date.fromisoformat(ph["ftc"])).days if ph.get("ftc") else None
        if fcw:
            ph["ftc_forecast_wx"] = fcw
    fcs = [ph["ftc_forecast"] for ph in pr.get("phases") or [] if ph.get("ftc_forecast")]
    if fcs:
        pr["completion_forecast"] = max(fcs)
    fws = [ph["ftc_forecast_wx"] for ph in pr.get("phases") or [] if ph.get("ftc_forecast_wx")]
    if fws:
        pr["completion_forecast_wx"] = max(fws)


def _decide(pr: Dict[str, Any], why_not_ai: str) -> Dict[str, Any]:
    """The dates shown as the plan: the AI model's where it answered, else the
    measured engine's - each with its source."""
    ai = pr.get("ai") or {}
    nxt = next((ph for ph in pr.get("phases") or [] if not ph.get("charged")), None)
    first_need = min((b["need_by"] for b in pr.get("blocks") or []
                      if b.get("need_by") and b.get("remaining_mwp", 0) > 0.01), default=None)
    engine = {"order_by": pr.get("first_order_by"), "tc": first_need,
              "ftc": nxt.get("ftc_forecast") if nxt else None}
    out: Dict[str, Any] = {"phase": nxt["name"] if nxt else None, "engine": engine}
    for k in ("order_by", "tc", "ftc"):
        if ai.get(k):
            out[k], out[f"{k}_source"] = ai[k], "ai"
        else:
            out[k], out[f"{k}_source"] = engine[k], "engine"
    out["source"] = "AI model" if ai else f"Measured engine - {why_not_ai}"
    out["confidence"], out["risk"] = ai.get("confidence"), ai.get("risk")
    return out


def _block_ftc(pl: Dict[str, Any], as_of: date, with_wx: bool) -> None:
    """Block FTC = modules done + the gap to charging, where modules are done
    at the LATER of: when the site can finish them (structure-driven), or
    when they land + 14 d receipt/inspection + the install time. A late delivery to a block whose
    structure is not ready anyway delays nothing (FY26-P08 Blk 7: capping
    holds it to mid-Feb, so modules landing in January cost no time)."""
    parts = pl.get("ftc_parts")
    if not parts or pl.get("ftc_actual"):
        return
    arrival = date.fromisoformat(pl["arrival"]) if pl.get("arrival_late_days") else None
    for key, site_key in (("ftc_forecast", "site_done"), ("ftc_forecast_wx", "site_done_wx")):
        if key == "ftc_forecast_wx" and not (with_wx and parts.get(site_key)):
            continue
        site = date.fromisoformat(parts[site_key])
        # Modules that land late still need receipt and inspection before
        # installation starts - the same 14-day site buffer as an on-time
        # delivery (on site -> FTC then reads ~41-43 d, as the standard 45 d
        # rule and the P6 baselines' 44 d median assume).
        by_supply = (arrival + timedelta(days=SITE_BUFFER_DAYS + parts["install_days"])) if arrival else None
        done = max(site, by_supply) if by_supply else site
        pl[key] = max(as_of, done + timedelta(days=parts["charge_gap_days"])).isoformat()
        if key == "ftc_forecast":
            parts["modules_done"] = done.isoformat()
            parts["held_by"] = "modules arriving late" if by_supply and by_supply > site else "site progress"


def _holding_stage(pl: Dict[str, Any]) -> Optional[str]:
    """The earliest stage not finished - what the block is waiting on."""
    return next((s["label"] for s in pl["stages"] if not s.get("missing") and not s.get("done")), None)


def _reason(pl: Dict[str, Any], lead: int, origin: Optional[str]) -> str:
    hold = _holding_stage(pl)
    stage = next((s for s in pl["stages"] if s["label"] == hold), None) if hold else None
    bits = []
    if stage:
        bits.append(f"{hold} {stage['pct']:.0f}% done")
        if stage.get("delay_days") and stage["delay_days"] > 0:
            bits.append(f"{stage['delay_days']} d behind baseline")
    bits.append(f"modules needed {pl['need_by']}")
    bits.append(f"{origin or 'domestic'} lead {lead} d")
    return "; ".join(bits)


def _status_label(pl: Dict[str, Any]) -> str:
    return {"late": "Late - order now", "order_now": "Order this month", "hold": "Hold",
            "covered": "Covered", "installed": "Installed", "no_dates": "No dates"}.get(pl.get("status"), "")
