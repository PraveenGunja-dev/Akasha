"""Block-level module ordering (branch feature/block-level-ordering).

The live Ordering Schedule (services/module_planner.py) times a phase's whole
balance against its FTC milestone. P6 is more precise than that: every solar
block has its own "Module Installation" activity carrying the block's MWp
(Material resource "Module - Construction", 894 blocks / 52 projects, ~17 MWp
each, checked 2026-10-07) in the order the site builds it:

    Piling MMS -> Pile capping -> MMS erection (torque tube, bracing, purlin)
    -> MMS - RFI Completion -> Module Installation -> Module RFI -> DC cable ...

So modules are needed block by block, across each block's installation window,
not all at FTC (Baiya Block-07 charged on 17-Mar-26 while its modules were
still going on until 31-Aug-26). This engine:

  1. reads each block's MWp, installed MWp and current P6 window;
  2. checks the window against the pace blocks actually achieve on that project
     (completed blocks: median 35 days vs 25 planned) and stretches a plan that
     is faster than the site has ever been - labelled as inferred;
  3. spreads each block's remaining MWp over its window -> MWp needed per month;
  4. nets that against modules already in the pipeline (site stock, in transit,
     ordered not yet dispatched) - the MRP step;
  5. moves each month's shortfall back by supplier lead time + a site buffer
     to the latest month the order can be placed;
  6. fits those orders into each origin's monthly quota (China / SEA / ALMM /
     DCR / ALCM, MWac): P1 first, then P2, then standard, earliest need first;
     each lot goes in the latest month up to its deadline that has room, else
     earlier, and only past its deadline - a delay - when nothing before it
     has room.

Delays carry through: a block cannot take modules until its MMS structure is
going up, so when MMS erection on a block has not started (or is slipping)
the module need starts no earlier than MMS start + the lag completed blocks
actually showed between the two. Each block is also checked against the
project's SCOD and LTA.

Block-wise only (user, 2026-10-07): a project with no block activities is
listed as not plannable rather than planned another way, so the gap shows.
Every figure is per P6 schedule (latest data date), read-only, with its basis.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.module_planner import LEAD_TIMES, DEFAULT_LEAD_TIME, CAP_LIMITS, DEFAULT_CAP, PRIORITY_RANKS

MODULE_RESOURCE = "Module - Construction"
SITE_BUFFER_DAYS = 15          # modules on site this long before installation starts
PACE_TOLERANCE = 1.25          # a plan up to 25% faster than achieved pace is accepted
BLOCK_RE = re.compile(r"\b(Block|BLK)\s*[- ]?\s*(\d+)", re.I)

# The schedule P6 currently names with the tracked project ID is the newest one
# (as module_deliveries.LATEST_P6). Planners replace a schedule by creating a
# new project under the tracked ID and renaming the old one "..._Old" (Baiya,
# Bandha, Aug-26); a stale local row of the old one must not be preferred.
LATEST_P6 = """
    SELECT DISTINCT ON (project_id) project_id, p6_object_id
    FROM p6_project WHERE project_id IS NOT NULL
    ORDER BY project_id, data_date DESC NULLS LAST, last_synced_at DESC NULLS LAST, p6_object_id DESC
"""


def _month(d: date) -> str:
    return d.strftime("%Y-%m")


def _d(x) -> Optional[date]:
    if x is None:
        return None
    return x.date() if isinstance(x, datetime) else x


def _block_label(name: str, fallback: str) -> str:
    m = BLOCK_RE.search(name or "")
    return f"Block-{int(m.group(2)):02d}" if m else fallback


def load_blocks(db: Session, p6_project_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    """Per P6 project: its block module-installation activities with MWp,
    installed MWp, current window, and the block's MMS RFI status."""
    if not p6_project_ids:
        return {}
    rows = db.execute(text(f"""
        WITH latest AS ({LATEST_P6})
        SELECT l.project_id, a.activity_id, a.name, a.status,
               a.start_date, a.finish_date, a.actual_start_date, a.actual_finish_date,
               a.baseline_start_date, a.baseline_finish_date,
               SUM(r.planned_units), SUM(COALESCE(r.actual_units, 0))
        FROM latest l
        JOIN p6_activity a ON a.project_object_id = l.p6_object_id
        JOIN p6_resource_assignment r ON r.activity_object_id = a.p6_object_id
        WHERE l.project_id = ANY(:p) AND r.resource_type = 'Material' AND r.resource_name = :res
        GROUP BY 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
    """), {"p": p6_project_ids, "res": MODULE_RESOURCE}).fetchall()
    rfi = db.execute(text(f"""
        WITH latest AS ({LATEST_P6})
        SELECT l.project_id, a.name, a.finish_date, a.actual_finish_date
        FROM latest l JOIN p6_activity a ON a.project_object_id = l.p6_object_id
        WHERE l.project_id = ANY(:p) AND a.name ~* 'MMS\\s*-?\\s*RFI'
    """), {"p": p6_project_ids}).fetchall()
    rfi_by = {(pid, _block_label(n, "")): (_d(f), _d(af)) for pid, n, f, af in rfi}
    # First MMS erection step on the block (torque tube / rafter): modules
    # follow the structure, so this is what a module start really waits on.
    mms = db.execute(text(f"""
        WITH latest AS ({LATEST_P6})
        SELECT l.project_id, a.name, a.start_date, a.actual_start_date, a.baseline_start_date
        FROM latest l JOIN p6_activity a ON a.project_object_id = l.p6_object_id
        WHERE l.project_id = ANY(:p) AND a.name ~* 'MMS\\s*Erection' AND a.name ~* 'Torque|Rafter'
    """), {"p": p6_project_ids}).fetchall()
    mms_by = {(pid, _block_label(n, "")): (_d(st), _d(ast), _d(bst)) for pid, n, st, ast, bst in mms}

    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for pid, aid, name, status, s, f, as_, af, bs, bf, plan, done in rows:
        label = _block_label(name, aid)
        r = rfi_by.get((pid, label))
        mm = mms_by.get((pid, label))
        out[pid].append({
            "block": label, "activity_id": aid, "name": (name or "").strip(),
            "mwp": round(float(plan or 0), 3), "installed_mwp": round(float(done or 0), 3),
            "start": _d(s), "finish": _d(f), "actual_start": _d(as_), "actual_finish": _d(af),
            "baseline_start": _d(bs), "baseline_finish": _d(bf),
            "mms_rfi_finish": r[0] if r else None, "mms_rfi_done": bool(r and r[1]),
            "mms_start": mm[0] if mm else None, "mms_actual_start": mm[1] if mm else None,
            "mms_baseline_start": mm[2] if mm else None,
        })
    for pid in out:
        out[pid].sort(key=lambda b: (b["start"] or date.max, b["block"]))
    return out


def observed_pace(blocks: List[Dict[str, Any]]) -> Optional[float]:
    """Median MWp/day of blocks this project has finished installing."""
    rates = [b["mwp"] / max(1, (b["actual_finish"] - b["actual_start"]).days)
             for b in blocks if b["actual_finish"] and b["actual_start"] and b["mwp"] > 0]
    return median(rates) if len(rates) >= 3 else None


def observed_lag(blocks: List[Dict[str, Any]]) -> Optional[int]:
    """Median days from MMS erection start to module installation start, on
    blocks where both have actually started."""
    lags = [(b["actual_start"] - b["mms_actual_start"]).days for b in blocks
            if b["actual_start"] and b["mms_actual_start"]]
    lags = [x for x in lags if x >= 0]
    return int(median(lags)) if len(lags) >= 3 else None


def block_need(b: Dict[str, Any], as_of: date, pace: float, lag: int = 0) -> Dict[str, Any]:
    """Remaining MWp of one block spread over the days it will be installed."""
    remaining = max(0.0, b["mwp"] - b["installed_mwp"])
    info = {"remaining_mwp": round(remaining, 3), "need_by_month": {}, "basis": "p6", "flags": []}
    if remaining <= 0.001 or b["actual_finish"]:
        info["remaining_mwp"] = 0.0
        return info
    # Slip against the plan baseline, as P6 itself now shows it.
    if b["baseline_finish"] and b["finish"]:
        info["slip_days"] = (b["finish"] - b["baseline_finish"]).days
    start = max(b["actual_start"] or b["start"] or as_of, as_of)
    finish = b["finish"] or start
    # Not started and the structure is not up yet: the modules wait for MMS.
    if not b["actual_start"] and not b["mms_actual_start"] and b["mms_start"]:
        earliest = max(b["mms_start"], as_of) + timedelta(days=lag)
        if earliest > start:
            shift = (earliest - start).days
            start, finish = earliest, max(finish, earliest) + timedelta(days=shift)
            info["flags"].append(f"held by MMS erection (+{shift} d)")
            info["basis"] = "mms-adjusted"
    if finish < as_of:                       # P6 says it should be done: needed now
        info["flags"].append("overdue")
        info["need_by_month"][_month(as_of)] = round(remaining, 3)
        info["window"] = [as_of.isoformat(), as_of.isoformat()]
        return info
    days = max(1, (finish - start).days)
    if remaining / days > pace * PACE_TOLERANCE:
        # Faster than this site has ever installed: stretch to the achieved pace.
        days = max(days, int(round(remaining / pace)))
        finish = start + timedelta(days=days)
        info["basis"] = "pace-adjusted" if info["basis"] == "p6" else info["basis"] + "+pace"
        info["flags"].append("plan faster than achieved pace")
    per_day = remaining / days
    need: Dict[str, float] = defaultdict(float)
    d = start
    while d < start + timedelta(days=days):
        need[_month(d)] += per_day
        d += timedelta(days=1)
    info["need_by_month"] = {m: round(v, 3) for m, v in sorted(need.items())}
    info["window"] = [start.isoformat(), finish.isoformat()]
    info["expected_finish"] = finish.isoformat()
    return info


def _date(v) -> Optional[date]:
    if not v:
        return None
    for fmt in ("%d-%b-%y", "%Y-%m-%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(str(v)[:11], fmt).date()
        except ValueError:
            continue
    return None


def plan_project(row: Dict[str, Any], blocks: List[Dict[str, Any]], as_of: date,
                 portfolio_pace: float, portfolio_lag: int,
                 buffer_days: int = SITE_BUFFER_DAYS) -> Dict[str, Any]:
    """One ordering row: block demand, netted against the module pipeline,
    shifted back by lead time to the month each order must be placed."""
    source = row.get("type") or "ALMM"
    lead = LEAD_TIMES.get(source, DEFAULT_LEAD_TIME)
    own_pace = observed_pace(blocks)
    pace = own_pace or portfolio_pace
    own_lag = observed_lag(blocks)
    lag = own_lag if own_lag is not None else portfolio_lag
    scod, lta = _date(row.get("scod")), _date(row.get("lta"))
    need: Dict[str, float] = defaultdict(float)
    detail = []
    for b in blocks:
        n = block_need(b, as_of, pace, lag)
        fin = _date(n.get("expected_finish")) if n.get("expected_finish") else None
        if fin and scod and fin > scod:
            n["flags"].append(f"installs after SCOD by {(fin - scod).days} d")
        if fin and lta and fin > lta:
            n["flags"].append(f"installs after LTA by {(fin - lta).days} d")
        for m, v in n["need_by_month"].items():
            need[m] += v
        detail.append({**{k: (v.isoformat() if isinstance(v, date) else v) for k, v in b.items()}, **n})

    # Pipeline already covering future installs: site stock, in transit, and
    # ordered but not yet dispatched (SAP, as the live schedule reads it).
    pipeline = max(0.0, float(row.get("module_inventory_mwp") or 0)) \
        + float(row.get("under_transit_mwp") or 0) + float(row.get("balance_dispatch_mwp") or 0)
    cover = pipeline
    shortfall: Dict[str, float] = {}
    for m in sorted(need):
        use = min(cover, need[m])
        cover -= use
        if need[m] - use > 0.001:
            shortfall[m] = round(need[m] - use, 3)

    # Order month = need month - (lead time + site buffer): the LATEST month
    # the lot can be ordered and still arrive in time.
    this_month = _month(as_of)
    block_total = sum(b["mwp"] for b in blocks)
    mwac = float(row.get("capacity_mwac") or 0)
    mwp_cap = float(row.get("capacity_mwp") or 0)
    dc_ac = (mwp_cap / mwac) if (mwac and mwp_cap) else (block_total / mwac if mwac else 1.35)
    orders: Dict[str, float] = defaultdict(float)
    late: Dict[str, float] = defaultdict(float)
    lots = []
    for m, v in shortfall.items():
        y, mo = int(m[:4]), int(m[5:7])
        place_by = date(y, mo, 1) - timedelta(days=lead + buffer_days)
        om = _month(place_by)
        if om < this_month:              # should already have been ordered
            orders[this_month] += v
            late[m] += v
        else:
            orders[om] += v
        lots.append({"need_month": m, "deadline": max(om, this_month), "late": om < this_month,
                     "mwp": round(v, 3), "mwac": round(v / dc_ac, 3)})

    block_mwp = sum(b["mwp"] for b in blocks)
    cap = float(row.get("capacity_mwp") or 0)
    installed = sum(b["installed_mwp"] for b in blocks)
    ordered = float(row.get("ordered_mwp") or 0)
    # How much is still to order, two ways that should agree: the blocks'
    # uninstalled MWp less the pipeline, and block MWp less what SAP holds as
    # ordered. A gap between them points at a P6 or SAP record to check.
    by_blocks = max(0.0, block_mwp - installed - pipeline)
    by_sap = max(0.0, block_mwp - ordered)
    open_detail = [d for d in detail if d["remaining_mwp"] > 0]
    after_scod = [d for d in open_detail if any("after SCOD" in f for f in d["flags"])]
    after_lta = [d for d in open_detail if any("after LTA" in f for f in d["flags"])]
    slips = [d.get("slip_days") for d in open_detail if d.get("slip_days") is not None]
    return {
        "id": row.get("id"), "project_name": row.get("project_name"), "p6_name": row.get("p6_name"),
        "cluster": row.get("cluster"), "type": source, "priority": row.get("priority"),
        "lead_days": lead, "buffer_days": buffer_days,
        "method": "block",
        "blocks_total": len(blocks), "blocks_open": sum(1 for b in blocks if not b["actual_finish"]),
        "block_mwp": round(block_mwp, 2), "capacity_mwp": cap,
        "coverage_pct": round(block_mwp / cap * 100, 1) if cap else None,
        "installed_mwp": round(sum(b["installed_mwp"] for b in blocks), 2),
        "pace_mwp_per_day": round(pace, 3),
        "pace_basis": "this project's completed blocks" if own_pace else "portfolio median (fewer than 3 blocks done here)",
        "mms_to_module_lag_days": lag,
        "lag_basis": "this project's started blocks" if own_lag is not None else "portfolio median",
        "scod": scod.isoformat() if scod else None, "lta": lta.isoformat() if lta else None,
        "blocks_after_scod": len(after_scod), "mwp_after_scod": round(sum(d["remaining_mwp"] for d in after_scod), 2),
        "blocks_after_lta": len(after_lta), "mwp_after_lta": round(sum(d["remaining_mwp"] for d in after_lta), 2),
        "median_slip_days": int(median(slips)) if slips else None,
        "blocks_held_by_mms": sum(1 for d in open_detail if any(f.startswith("held by MMS") for f in d["flags"])),
        "verify": {
            "block_mwp": round(block_mwp, 2), "capacity_mwp": cap, "sap_ordered_mwp": round(ordered, 2),
            "installed_mwp": round(installed, 2), "pipeline_mwp": round(pipeline, 2),
            "to_order_by_blocks_mwp": round(by_blocks, 2), "to_order_by_sap_mwp": round(by_sap, 2),
            "agree": abs(by_blocks - by_sap) <= max(1.0, 0.02 * block_mwp),
        },
        "pipeline_mwp": round(pipeline, 2),
        "need_by_month": {m: round(v, 2) for m, v in sorted(need.items())},
        "shortfall_by_month": shortfall,
        "orders_by_month": {m: round(v, 2) for m, v in sorted(orders.items())},
        "orders_unconstrained_by_month": {m: round(v, 2) for m, v in sorted(orders.items())},
        "dc_ac_ratio": round(dc_ac, 3),
        "origin_known": source in CAP_LIMITS,
        "lots": lots,
        "late_need_mwp": round(sum(late.values()), 2),
        "new_order_mwp": round(sum(orders.values()), 2),
        "ftc_method_balance_mwp": row.get("balance_ordering_mwp"),
        "ftc_method_by_month": row.get("month_mwp") or {},
        "blocks": detail,
    }


def _add_months(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + n
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def allocate_quotas(projects: List[Dict[str, Any]], this_month: str, horizon: int = 24) -> Dict[str, Any]:
    """Fit every block plan's order lots into each origin's monthly quota (MWac).

    Priority order: P1, P2, standard; within that, earliest need first. A lot
    goes into the latest month up to its deadline that still has room (orders
    stay small and close to need), then into earlier months, never before the
    current month; whatever still does not fit goes past the deadline - a
    quota delay, reported on the project. Lots split across months as needed.
    """
    months = [_add_months(this_month, i) for i in range(horizon)]
    room = {}
    lots_by_origin = defaultdict(list)
    for p in projects:
        if p.get("method") != "block":
            continue
        p["allocated_by_month"] = defaultdict(float)
        p["quota_delayed_mwp"] = 0.0
        p["quota_pulled_early_mwp"] = 0.0
        p["max_quota_delay_months"] = 0
        for lot in p.get("lots", []):
            lots_by_origin[p["type"]].append((p, lot))
    used = defaultdict(lambda: defaultdict(float))
    for origin, items in lots_by_origin.items():
        cap = CAP_LIMITS.get(origin, DEFAULT_CAP)
        room = {m: cap for m in months}
        items.sort(key=lambda it: (PRIORITY_RANKS.get(it[0].get("priority") or "standard", 3),
                                   it[1]["need_month"], it[1]["deadline"]))
        for p, lot in items:
            left = lot["mwac"]
            ratio = lot["mwp"] / lot["mwac"] if lot["mwac"] else 1.0
            dl = lot["deadline"]
            order = [m for m in reversed(months) if m <= dl] + [m for m in months if m > dl]
            for m in order:
                if left <= 1e-6:
                    break
                take = min(left, room[m])
                if take <= 1e-6:
                    continue
                room[m] -= take
                left -= take
                used[origin][m] += take
                p["allocated_by_month"][m] += take * ratio
                if m > dl:
                    p["quota_delayed_mwp"] += take * ratio
                    gap = (int(m[:4]) * 12 + int(m[5:7])) - (int(dl[:4]) * 12 + int(dl[5:7]))
                    p["max_quota_delay_months"] = max(p["max_quota_delay_months"], gap)
                elif m < dl:
                    p["quota_pulled_early_mwp"] += take * ratio
            if left > 1e-6:          # beyond the horizon: report, do not drop
                p["quota_delayed_mwp"] += left * ratio
                p.setdefault("unplaced_mwp", 0.0)
                p["unplaced_mwp"] += left * ratio
    for p in projects:
        if p.get("method") == "block":
            p["orders_by_month"] = {m: round(v, 2) for m, v in sorted(p.pop("allocated_by_month").items())}
            for k in ("quota_delayed_mwp", "quota_pulled_early_mwp", "unplaced_mwp"):
                if k in p:
                    p[k] = round(p[k], 2)
    return {
        o: {"cap_mwac": CAP_LIMITS.get(o, DEFAULT_CAP), "known_origin": o in CAP_LIMITS,
            "used_mwac_by_month": {m: round(v, 1) for m, v in sorted(ms.items())}}
        for o, ms in used.items()
    }


def build_block_plan(db: Session, rows: List[Dict[str, Any]], as_of: Optional[date] = None,
                     buffer_days: int = SITE_BUFFER_DAYS) -> Dict[str, Any]:
    """Block-level plan for the live schedule's rows (same projects, same SAP
    supply figures), with the FTC plan kept alongside for comparison."""
    import models
    as_of = as_of or date.today()
    ids = [r["id"] for r in rows if r.get("id")]
    p6_of = {m.id: m.project_id for m in db.query(models.ProjectMapping).filter(models.ProjectMapping.id.in_(ids))}
    blocks_by_p6 = load_blocks(db, sorted({v for v in p6_of.values() if v}))

    every = [b for bs in blocks_by_p6.values() for b in bs]
    portfolio_pace = observed_pace(every) or 0.48
    portfolio_lag = observed_lag(every) or 0

    projects = []
    for row in rows:
        blocks = blocks_by_p6.get(p6_of.get(row.get("id")), [])
        if blocks:
            projects.append(plan_project(row, blocks, as_of, portfolio_pace, portfolio_lag, buffer_days))
        else:
            # Block-wise only: no fallback plan, the gap is listed instead.
            projects.append({
                "id": row.get("id"), "project_name": row.get("project_name"), "p6_name": row.get("p6_name"),
                "cluster": row.get("cluster"), "type": row.get("type"), "priority": row.get("priority"),
                "method": "none",
                "reason": "no block-level Module Installation activities (resource 'Module - Construction') in P6",
                "orders_by_month": {}, "new_order_mwp": None,
                "ftc_method_balance_mwp": row.get("balance_ordering_mwp"),
                "capacity_mwp": row.get("capacity_mwp"), "sap_ordered_mwp": row.get("ordered_mwp"),
            })

    quota = allocate_quotas(projects, _month(as_of))
    months = sorted({m for p in projects for m in (p.get("orders_by_month") or {})})
    by_type: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for p in projects:
        for m, v in (p.get("orders_by_month") or {}).items():
            by_type[p.get("type") or "ALMM"][m] += float(v or 0)
    return {
        "as_of": as_of.isoformat(), "months": months,
        "assumptions": {
            "site_buffer_days": buffer_days, "pace_tolerance": PACE_TOLERANCE,
            "portfolio_pace_mwp_per_day": round(portfolio_pace, 3),
            "portfolio_mms_to_module_lag_days": portfolio_lag,
            "lead_days": dict(LEAD_TIMES), "module_resource": MODULE_RESOURCE,
            "notes": [
                "Need dates come from each block's current P6 Module Installation window.",
                "A window faster than the project's achieved pace is stretched to that pace (inferred).",
                "Pipeline = site stock + in transit + ordered not yet dispatched (SAP).",
                "Order month = need month - (supplier lead time + site buffer).",
                "A block whose MMS erection has not started waits for it: need starts at MMS start + the observed lag.",
                "Each block's expected install finish is checked against SCOD and LTA.",
                "Block-wise only: projects without block activities are listed, not planned.",
                "Orders fit each origin's monthly quota (MWac): P1, P2, then standard; earliest need first; latest month up to the deadline with room, then earlier, then late.",
                "A project whose origin is not in the master takes the default quota pool and is flagged.",
            ],
        },
        "orders_by_type_month": {t: {m: round(v, 2) for m, v in sorted(ms.items())} for t, ms in by_type.items()},
        "quota_by_origin": quota,
        "projects": projects,
        "coverage": {
            "block_projects": sum(1 for p in projects if p["method"] == "block"),
            "no_block_data_projects": sum(1 for p in projects if p["method"] == "none"),
        },
    }
