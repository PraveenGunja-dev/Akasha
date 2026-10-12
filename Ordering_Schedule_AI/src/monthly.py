"""Month-wise Module Requirement at Site (MWp / MWac) - rule engine and AI.

What the sheet's monthly cells are (verified on all 43 planned cells,
build_datasets.py report): a phase's requirement, phase MWac x OL, placed in
its TC month (FTC - 45 d). The order goes out one lead time earlier.

Quantity (Planning Rules): only the Balance Ordering is planned. Phases sorted
by order date each get their full requirement from the balance until it runs
out; the last funded phase is truncated, later phases are not ordered.

Two ways a month's requirement is timed - the planner's own 'Monthly plan
timed by' column:
  FTC date    each funded phase lands in its TC month.
  Site speed  where P6 measures a structure pace and balance remains, modules
              are needed as structures are built: current stock (inventory +
              in transit) is used first, then each month needs what the site
              will build that month. 'Ordering earlier only adds stock in the
              yard.'

Rule engine: TC from the P6 FTC, order = TC - 136 d (China/SEA) / 98 d (ALMM,
ALCM, DCR). AI: TC from the AI effective FTC (P6 FTC + ML site-readiness
shift, or LTA when transmission binds), order-by = need date - measured P90
lead time (Ariba), so even a late delivery meets the need.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from features import RULE_LEAD_DAYS, TC_BUFFER_DAYS


# Planning Rules, 'Vendor capacity levelling': monthly ordering ceilings, MWac.
VENDOR_QUOTA_MWAC = {"China": 750, "SEA": 500, "ALMM": 500, "ALCM": 100, "DCR": 100}


@dataclass
class Phase:
    label: str
    mwac: float
    ftc: date


def month_key(d: date) -> str:
    return d.strftime("%b-%y")


def fund(phases: list[Phase], balance_mwac: float, lead_days: int | None) -> list[tuple[Phase, float]]:
    """Planning Rules sequencing: by order date, full requirement until the balance runs out."""
    lead = lead_days or 0
    order = sorted(phases, key=lambda p: p.ftc - timedelta(days=TC_BUFFER_DAYS + lead))
    left, out = max(balance_mwac or 0.0, 0.0), []
    for p in order:
        q = min(p.mwac, left)
        if q > 1e-6:
            out.append((p, q))
            left -= q
    return out


def _rows(buckets: dict, ol: float, lead_for_order: float | None, today: date) -> list[dict]:
    rows = []
    for key in sorted(buckets, key=lambda k: buckets[k]["first_need"]):
        b = buckets[key]
        need = b["first_need"]
        order_by = need - timedelta(days=round(lead_for_order)) if lead_for_order is not None else None
        rows.append({
            "month": key, "required_at_site_mwp": round(b["mwac"] * ol, 1), "required_at_site_mwac": round(b["mwac"], 1),
            "need_date": need.isoformat(),
            "order_by_date": order_by.isoformat() if order_by else None,
            "order_month": month_key(max(order_by, today)) if order_by else None,
            "overdue": bool(order_by and order_by < today),
            "phases": b["phases"],
        })
    return rows


def rule_plan(phases: list[Phase], balance_mwac: float, ol: float, vendor: str, today: date) -> list[dict]:
    """The current engine: funded phases in their P6-based TC month."""
    lead = RULE_LEAD_DAYS.get(vendor)
    buckets: dict = defaultdict(lambda: {"mwac": 0.0, "phases": [], "first_need": date.max})
    for p, q in fund(phases, balance_mwac, lead):
        tc = p.ftc - timedelta(days=TC_BUFFER_DAYS)
        b = buckets[month_key(tc)]
        b["mwac"] += q
        b["phases"].append(f"{p.label} ({q:g} MWac)")
        b["first_need"] = min(b["first_need"], tc)
    return _rows(buckets, ol, lead, today)


def ai_phase_plan(funded: list[tuple[Phase, float, date]], ol: float, lead_p90: float, today: date) -> list[dict]:
    """FTC-date timing on the AI effective FTC. funded: (phase, MWac, effective FTC)."""
    buckets: dict = defaultdict(lambda: {"mwac": 0.0, "phases": [], "first_need": date.max})
    for p, q, eff in funded:
        tc = eff - timedelta(days=TC_BUFFER_DAYS)
        b = buckets[month_key(tc)]
        b["mwac"] += q
        b["phases"].append(f"{p.label} ({q:g} MWac)")
        b["first_need"] = min(b["first_need"], tc)
    return _rows(buckets, ol, lead_p90, today)


def ai_site_paced_plan(balance_mwac: float, ol: float, pace_mwdc_day: float, backlog_mwdc: float,
                       stock_mwp: float, structure_left_mwdc: float, today: date, lead_p90: float,
                       max_days: int = 1500) -> list[dict]:
    """Site-speed timing: modules are needed as structures become ready.

    Mounting demand = the structure backlog already waiting for modules, then
    the structure the site builds each day at its measured P6 pace. Stock
    (inventory + in transit) covers demand first; what is left over is the
    requirement to arrive, until the balance is used. Module MWp ~ MWdc.
    """
    need_left = max(balance_mwac or 0.0, 0.0) * ol      # MWp still to arrive
    stock = max(stock_mwp or 0.0, 0.0)
    buckets: dict = defaultdict(lambda: {"mwac": 0.0, "phases": [], "first_need": date.max})

    def take(day: date, demand: float):
        nonlocal stock, need_left
        use = min(stock, demand)
        stock -= use
        req = min(demand - use, need_left)
        if req > 1e-6:
            b = buckets[month_key(day)]
            b["mwac"] += req / ol
            b["first_need"] = min(b["first_need"], day)
            need_left -= req

    take(today, max(backlog_mwdc or 0.0, 0.0))
    left = max(structure_left_mwdc or 0.0, 0.0)
    day = today
    for _ in range(max_days):
        if need_left <= 1e-6 or left <= 1e-6 or pace_mwdc_day <= 0:
            break
        day += timedelta(days=1)
        built = min(pace_mwdc_day, left)
        left -= built
        take(day, built)
    if need_left > 1e-6:   # balance beyond the remaining structure scope: needed when the last structure is done
        b = buckets[month_key(day)]
        b["mwac"] += need_left / ol
        b["first_need"] = min(b["first_need"], day)
    for b in buckets.values():
        b["phases"] = ["paced by structure completion"]
    return _rows(buckets, ol, lead_p90, today)


def total_mwp(rows: list[dict]) -> float:
    return round(sum(r["required_at_site_mwp"] for r in rows), 1)
