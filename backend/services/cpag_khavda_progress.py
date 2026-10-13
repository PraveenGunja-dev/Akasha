"""
Procurement, Construction Progress and Manpower tables of the Khavda Solar pack,
summed over the Solar Khavda projects in P6.

Same source and rules as the Rajasthan pack (services/cpag_solar_progress.py):
P6 Material resource assignments carry quantities with a unit of measure,

    "<item> - Supply"        -> units received at site, per "Receipt at Site" lot
    "<item> - Construction"  -> units installed, per block

and Labor assignments carry the hours behind manpower. Nothing comes from the
issued report or from SAP (whose delivered quantity equals ordered on every line).

Differences from Rajasthan, which has one project per pack:
  * Scope is the sum of P6's own planned quantity (Rajasthan keeps the template's).
  * A row is summed over the projects P6 can support it for; the count is returned
    so the viewer can show "n of N projects".
  * Units are P6's (Module is MWdc, MMS is tables, cables are km).
"""
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.cpag_solar_progress import (
    FORECAST_MONTHS, PROCUREMENT_ROWS, SUPPLY_RECONCILE_TOL,
    _activity_items, _binding, _first_forecast_month, _material_items,
    _month_actual_known, _norm, _slot, _split_block, _summarise, _unit_items,
    fetch_procurement_rows,
)

HOURS_PER_DAY = 8.0   # P6 Labor units are hours (CLAUDE.md, verified platform-wide)

# Template order of the Procurement page -> label in PROCUREMENT_ROWS, with P6's unit.
PROCUREMENT_TEMPLATE = [
    ("Module", "MWdc"), ("MMS - FT", "Tables"), ("Inverter", "Nos"), ("IDT", "Nos"),
    ("HT Panel", "Nos"), ("LT Panel", "Nos"), ("HT Cable", "Km"), ("LT Cable", "Km"),
    ("DC Cable", "Km"), ("Robotic Module Cleaning System", "Nos"),
]

# Khavda files each package's LOI / PO Release milestone under varying WBS names
# ("MODULE (IMPORTED FROM CHINA)", "MMS - TRACKER", ...). A row's release status
# looks at the package's main equipment only: WBS names matching `include`, never
# its accessories (fasteners, canopy, rebar ...) or employer-supplied items.
_ACCESSORY = r"clamps|fasteners|hangers|messenger|support|structure|employer|rebar|rail|bolt|sheeting|station|fencing|gate|shed"
PO_RELEASE_WBS = {
    "Module": (r"^module", r"employer"),
    "MMS - FT": (r"^mms", r"employer"),
    "Inverter": (r"^inverter", r"structure|canopy|fasteners|screw|beam"),
    "IDT": (r"^idt", _ACCESSORY),
    "HT Panel": (r"^ht panel", _ACCESSORY),
    "LT Panel": (r"^lt panel", _ACCESSORY),
    "HT Cable": (r"^ht cable", _ACCESSORY),
    "LT Cable": (r"^lt cables?", _ACCESSORY),
    "DC Cable": (r"^dc cable", _ACCESSORY),
    "Robotic Module Cleaning System": (r"^robotic (module\s+)?cleaning system - robots?", r"fasteners|structure"),
}

_IDT = "IDT - Construction"
# Template order of the Construction Progress page. `material` rows are P6
# installed quantity; `activity` rows are block activities weighted by the
# block's own IDT count; `mc4_voc` is MWdc, a block counting once both steps are
# done. `labor` lists the activities whose Labor feeds the Manpower page (None =
# no row there). `uom` is the unit P6 books the quantity in.
CONSTRUCTION_TEMPLATE: List[Dict[str, Any]] = [
    {"label": "Piling", "uom": "Nos", "material": ["Piling Stub - MMS - Construction"],
     "labor": ["Piling - MMS (Marking, Auguring & Concreting)"]},
    {"label": "Tracker up to Torque Tube", "uom": "Tables", "material": ["MMS - Rafter - Construction"],
     "labor": ["MMS Erection - Torque Tube/Raftar", "MMS Erection - Torque Tube/Rafter"]},
    {"label": "Tracker up to Transmission Shaft with Purlin", "uom": "Tables",
     "material": ["MMS - Bracing - Construction"], "labor": None},
    {"label": "Module erection", "uom": "MWdc", "material": ["Module - Construction"],
     "labor": ["Module Installation"]},
    {"label": "Transformer foundation up to rail", "uom": "Nos", "activity": "IDT Foundation Up To Rail",
     "labor": ["IDT Foundation Up To Rail"]},
    {"label": "HT/LT Slab", "uom": "Nos", "activity": "HT & LT Station - Slab",
     "labor": ["HT & LT Station - Slab"]},
    {"label": "HT LT Panel Shed & Sheeting", "uom": "Nos", "activity": "HT & LT Station - Shed Installation",
     "labor": ["HT & LT Station - Shed Installation", "HT & LT Station - Sheeting Installation"]},
    {"label": "Transformer foundation Completion", "uom": "Nos",
     "activity": "IDT Foundation - Grade Slab Casting & Dyke Wall",
     "labor": ["IDT Foundation - Grade Slab Casting & Dyke Wall"]},
    {"label": "IDT Erection", "uom": "Nos", "material": [_IDT], "labor": ["IDT Erection"]},
    {"label": "HT Panel Erection", "uom": "Nos", "material": ["HT Panel - Construction"],
     "labor": ["HT Panel Erection"]},
    {"label": "LT Panel Erection", "uom": "Nos", "material": ["LT Panel - Construction"],
     "labor": ["LT Panel Erection"]},
    {"label": "Inverter erection", "uom": "Nos", "material": ["Invertor - Construction"],
     "labor": ["Inverter Installation"]},
    {"label": "LT Cable Laying", "uom": "Km", "material": ["LT Cable - Construction"],
     "labor": ["LT Cable Laying"]},
    {"label": "HT Cable Laying", "uom": "Km", "material": ["HT Cable - Construction"],
     "labor": ["HT Cable Laying"]},
    {"label": "DC Cable", "uom": "Km", "material": ["DC Cable - Construction"],
     "labor": ["DC Cable Laying"]},
    {"label": "MC4 & VOC testing", "uom": "MWdc", "mc4_voc": True,
     "labor": ["Module Interconnection & MC4 Termination", "VOC Testing"]},
    {"label": "Robots Module Cleaning", "uom": "Nos", "material": ["Robots - Construction"],
     "labor": ["Robot Installation"]},
]


def khavda_solar_projects(db: Session) -> List[Dict[str, Any]]:
    rows = db.execute(text("""
        SELECT DISTINCT p6.p6_object_id, p6.name, p6.data_date
        FROM p6_project p6
        JOIN project_mapping pm ON p6.name = pm.project_name_from_p6
        WHERE pm.cluster = 'Solar Khavda'
          AND EXISTS (SELECT 1 FROM p6_activity a WHERE a.project_object_id = p6.p6_object_id LIMIT 1)
        ORDER BY p6.name
    """)).fetchall()
    return [{"obj": r[0], "name": r[1], "data_date": r[2]} for r in rows]


def _num(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(float(v), 2)


# ── Procurement ─────────────────────────────────────────────────────────────
def _po_released(db: Session, obj: int, label: str) -> Optional[bool]:
    """True when every LOI / PO Release milestone of the package's main equipment
    is complete in P6, False when any is open, None when the project has none."""
    include, exclude = PO_RELEASE_WBS[label]
    rows = db.execute(text("""
        SELECT status FROM p6_activity
        WHERE project_object_id = :o AND name ILIKE '%LOI / PO Release%'
          AND wbs_name ~* :inc AND wbs_name !~* :exc
    """), {"o": obj, "inc": include, "exc": exclude}).fetchall()
    if not rows:
        return None
    return all(r[0] == "Completed" for r in rows)


def fetch_procurement(db: Session, projects: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    order = [s["label"] for s in PROCUREMENT_ROWS]
    agg: Dict[str, Dict[str, Any]] = {
        lbl: {"scope": 0.0, "delivered": 0.0, "forecast": [0.0] * FORECAST_MONTHS,
              "ordered": 0.0, "to_order": 0.0, "n": 0, "n_released": 0, "n_unreleased": 0}
        for lbl, _ in PROCUREMENT_TEMPLATE
    }
    for p in projects:
        rows = fetch_procurement_rows(db, p["obj"], today)
        for lbl, _ in PROCUREMENT_TEMPLATE:
            r = rows[order.index(lbl)]
            if r is None:
                continue
            a = agg[lbl]
            a["n"] += 1
            a["scope"] += r["scope"]
            a["delivered"] += r["delivered"]
            for k, v in enumerate(r["forecast"]):
                a["forecast"][k] += v
            released = _po_released(db, p["obj"], lbl)
            if released is True:
                a["ordered"] += max(r["scope"], r["delivered"])
                a["n_released"] += 1
            elif released is False:
                a["to_order"] += r["scope"]
                a["n_unreleased"] += 1
    rows_out: List[Optional[Dict[str, Any]]] = []
    for lbl, uom in PROCUREMENT_TEMPLATE:
        a = agg[lbl]
        if not a["n"]:
            rows_out.append(None)
            continue
        # Ordered / Balance only when P6 states the PO release for every project in
        # the row; a partial sum next to the full Scope would not reconcile.
        known = (a["n_released"] + a["n_unreleased"]) == a["n"]
        rows_out.append({
            "label": lbl, "uom": uom, "n": a["n"],
            "scope": _num(a["scope"]), "delivered": _num(a["delivered"]),
            "forecast": [_num(v) for v in a["forecast"]],
            "ordered": _num(a["ordered"]) if known else None,
            "balance": _num(a["to_order"]) if known else None,
        })
    return {"rows": rows_out, "n_projects": len(projects)}


# ── Construction progress ───────────────────────────────────────────────────
def _project_items(db: Session, obj: int) -> Dict[str, Optional[List[Dict[str, Any]]]]:
    material = _material_items(db, obj)
    acts = _activity_items(db, obj)
    module_by_block: Dict[str, float] = {}
    for i in material.get("Module - Construction", []):
        block, _ = _split_block(i["name"])
        if block:
            module_by_block[block] = module_by_block.get(block, 0.0) + i["planned"]
    idt_by_block: Dict[str, float] = {}
    for i in material.get(_IDT, []):
        block, _ = _split_block(i["name"])
        if block:
            idt_by_block[block] = idt_by_block.get(block, 0.0) + i["planned"]

    out: Dict[str, Optional[List[Dict[str, Any]]]] = {}
    for spec in CONSTRUCTION_TEMPLATE:
        items = None
        if "material" in spec:
            items = _binding(material, spec["material"])
        elif "activity" in spec:
            found = acts.get(_norm(spec["activity"]))
            items = _unit_items(found, idt_by_block) if found else None
        elif spec.get("mc4_voc"):
            voc = acts.get("voc testing", [])
            mc4 = {i["block"]: i for i in acts.get("module interconnection & mc4 termination", [])}
            merged = [{**v, "completed": v["completed"] and bool(mc4.get(v["block"], {}).get("completed"))}
                      for v in voc if v["block"] in mc4]
            items = _unit_items(merged, module_by_block) if merged else None
        out[spec["label"]] = items or None
    return out


def fetch_construction(db: Session, projects: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    first_fc = _first_forecast_month(today)
    pooled: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    count: Dict[str, int] = defaultdict(int)
    for p in projects:
        for lbl, items in _project_items(db, p["obj"]).items():
            if items:
                pooled[lbl].extend(items)
                count[lbl] += 1
    # A month's actual is reported only when every project's P6 reaches that month.
    known = bool(projects) and all(_month_actual_known(p["data_date"], today) for p in projects)
    rows: List[Optional[Dict[str, Any]]] = []
    for spec in CONSTRUCTION_TEMPLATE:
        items = pooled.get(spec["label"])
        if not items:
            rows.append(None)
            continue
        s = _summarise(items, today, first_fc, known)
        scope = sum(i["planned"] for i in items)
        rows.append({
            "label": spec["label"], "uom": spec["uom"], "n": count[spec["label"]],
            "scope": _num(scope), "completed": _num(s["completed"]),
            "balance": _num(max(scope - s["completed"], 0.0)),
            "month_plan": _num(s["month_plan"]), "month_actual": _num(s["month_actual"]),
            "forecast": [_num(v) for v in s["forecast"]], "target": s["target"],
        })
    return {"rows": rows, "n_projects": len(projects), "actual_known": known}


# ── Manpower ────────────────────────────────────────────────────────────────
def _month_index(d: datetime) -> int:
    return d.year * 12 + d.month


def _spread_forward(acc: List[float], start: Optional[datetime], finish: Optional[datetime],
                    units: float, first_fc: date, data_date: Optional[datetime]) -> None:
    """Remaining mandays, evenly over the activity's remaining window (the later
    of its start and the P6 data date, to its forecast finish); only the share
    that falls in a forecast month is kept. Work finishing before the first
    forecast month belongs to an earlier month and is not shown."""
    if finish is None:
        return
    lo = max(d for d in (start, data_date) if d) if (start or data_date) else finish
    fc0 = datetime(first_fc.year, first_fc.month, 1)
    if finish <= lo:                         # overdue: all of it falls at one point
        k = _month_index(finish) - _month_index(fc0)
        if 0 <= k < FORECAST_MONTHS:
            acc[k] += units
        return
    span = (finish - lo).total_seconds()
    cur = lo
    while cur < finish:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = min(nxt, finish)
        k = _month_index(cur) - _month_index(fc0)
        if 0 <= k < FORECAST_MONTHS:
            acc[k] += units * (end - cur).total_seconds() / span
        cur = end


def _days_in(first_fc: date, k: int) -> int:
    idx = first_fc.year * 12 + first_fc.month - 1 + k
    y, m = divmod(idx, 12)
    start = date(y, m + 1, 1)
    nxt = date(y + (m == 11), (m + 1) % 12 + 1, 1)
    return (nxt - start).days


def fetch_manpower(db: Session, projects: List[Dict[str, Any]], today: date,
                   construction: Dict[str, Any]) -> Dict[str, Any]:
    first_fc = _first_forecast_month(today)
    by_activity: Dict[str, str] = {}
    for spec in CONSTRUCTION_TEMPLATE:
        for a in spec.get("labor") or []:
            by_activity[_norm(a)] = spec["label"]
    mandays: Dict[str, List[float]] = {lbl: [0.0] * FORECAST_MONTHS for lbl in by_activity.values()}
    for p in projects:
        rows = db.execute(text("""
            SELECT a.name, ra.planned_units, ra.actual_units, ra.remaining_units, a.start_date, a.finish_date
            FROM p6_resource_assignment ra
            JOIN p6_activity a ON a.p6_object_id = ra.activity_object_id
                              AND a.project_object_id = ra.project_object_id
            WHERE ra.project_object_id = :o AND ra.resource_type = 'Labor'
              AND a.wbs_name ILIKE 'CONSTRUCTION%'
        """), {"o": p["obj"]}).fetchall()
        for name, planned, actual, remaining, start, finish in rows:
            _, key = _split_block(name)
            lbl = by_activity.get(key)
            if not lbl:
                continue
            rem = float(remaining) if remaining is not None else max(float(planned or 0) - float(actual or 0), 0.0)
            if rem <= 0:
                continue
            _spread_forward(mandays[lbl], start, finish, rem / HOURS_PER_DAY, first_fc, p["data_date"])

    cons = {r["label"]: r for r in construction["rows"] if r}
    rows: List[Optional[Dict[str, Any]]] = []
    totals = [0.0] * FORECAST_MONTHS
    for spec in CONSTRUCTION_TEMPLATE:
        if not spec.get("labor") or spec["label"] not in cons:
            rows.append(None)
            continue
        c = cons[spec["label"]]
        need = [mandays[spec["label"]][k] / _days_in(first_fc, k) for k in range(FORECAST_MONTHS)]
        for k, v in enumerate(need):
            totals[k] += v
        rows.append({
            "label": spec["label"], "uom": c["uom"], "scope": c["scope"],
            "completed": c["completed"], "balance": c["balance"],
            "forecast": [round(v) for v in need],
        })
    return {"rows": rows, "total": [round(v) for v in totals]}


# ── Commissioning schedule, charging, PSS dates, robots ─────────────────────
_BLOCK_MILESTONE = re.compile(r"^block[\s-]*(\d+)\s*-\s*(COD|First Time Charging)\s*$", re.I)
_PLOT_IN_NAME = re.compile(r"_((?:SE|S|A)\d+[A-Za-z]?)_", re.I)
# Template PSS rows -> P6 milestone names ("PSS-7 Charging ...", "NHPC PSS Charging").
PSS_ROWS = [("PSS-11", r"^pss-0?11 charging"), ("PSS-12", r"^pss-0?12 charging"),
            ("PSS-14", r"^pss-0?14 charging"), ("PSS-07", r"^pss-0?7 charging"),
            ("NHPC", r"^nhpc pss charging"), ("PSS-18", r"^pss-0?18 charging")]


def _plot_label(name: str, mapped: Optional[str]) -> str:
    """The plot as P6 names it; the register's plot_no is blank or off for a few
    projects (e.g. ARE55L_A15b is registered under A01)."""
    m = _PLOT_IN_NAME.search(name or "")
    if m:
        return m.group(1)
    if mapped:
        return mapped
    return "NHPC" if "NHPC" in (name or "").upper() else "-"


def _fy_months(today: date) -> List[date]:
    y = today.year if today.month >= 4 else today.year - 1
    return [date(y + (m > 12), (m - 1) % 12 + 1, 1) for m in range(4, 16)]


def _month_slot(dt: Optional[datetime], months: List[date]) -> Optional[int]:
    if dt is None:
        return None
    for i, m in enumerate(months):
        if (dt.year, dt.month) == (m.year, m.month):
            return i
    return None


def fetch_commissioning(db: Session, projects: List[Dict[str, Any]], today: date) -> Dict[str, Any]:
    """Block COD / First Time Charging from P6, in MW.

    P6 records no block capacity, so each project's registered MWac is split over
    its blocks in proportion to P6's module MWdc per block; the blocks add back to
    the register's capacity."""
    mapped = {r[0]: (r[1], float(r[2] or 0)) for r in db.execute(text(
        "SELECT project_name_from_p6, plot_no, capacity_mwac FROM project_mapping WHERE cluster = 'Solar Khavda'"))}
    months = _fy_months(today)
    first_fc = _first_forecast_month(today)
    budget = [0.0] * 12
    actual = [0.0] * 12
    actual_done = [0.0] * 12
    out_budget = out_actual = 0.0
    planned_to_date = commissioned = 0.0
    last_cod: Optional[datetime] = None
    ftc: List[Dict[str, float]] = [defaultdict(float) for _ in range(FORECAST_MONTHS)]
    blocks_mw = blocks_all = 0
    mw_all = 0.0
    now = datetime.combine(today, datetime.min.time())
    for p in projects:
        plot, cap = mapped.get(p["name"], (None, 0.0))
        label = _plot_label(p["name"], plot)
        mod: Dict[str, float] = defaultdict(float)
        for i in _material_items(db, p["obj"]).get("Module - Construction", []):
            b, _ = _split_block(i["name"])
            if b:
                mod[b] += i["planned"]
        total_mod = sum(mod.values())
        rows = db.execute(text("""
            SELECT name, status, baseline_finish_date, finish_date, actual_finish_date
            FROM p6_activity WHERE project_object_id = :o AND name ~* '(COD|First Time Charging)$'
        """), {"o": p["obj"]}).fetchall()
        for name, status, base, fin, act in rows:
            m = _BLOCK_MILESTONE.match(name or "")
            if not m:
                continue
            blocks_all += 1
            q = mod.get(m.group(1))
            if not q or not total_mod or not cap:
                continue
            mw = cap * q / total_mod
            blocks_mw += 1
            done = status == "Completed"
            when = (act or fin) if done else fin
            if m.group(2).upper() == "COD":
                mw_all += mw
                if base and base <= now:
                    planned_to_date += mw
                if done:
                    commissioned += mw
                elif fin and (last_cod is None or fin > last_cod):
                    last_cod = fin
                k = _month_slot(base, months)
                if k is None:
                    out_budget += mw if base else 0.0
                else:
                    budget[k] += mw
                k = _month_slot(when, months)
                if k is None:
                    out_actual += mw if when else 0.0
                else:
                    actual[k] += mw
                    if done:
                        actual_done[k] += mw
            elif not done:
                k = _slot(fin, first_fc)
                if k is not None:
                    ftc[k][label] += mw
    return {
        "months": [m.strftime("%b-%y") for m in months],
        "budget": [round(v, 1) for v in budget], "actual": [round(v, 1) for v in actual],
        "actual_done": [round(v, 1) for v in actual_done],
        "outside_budget": round(out_budget, 1), "outside_actual": round(out_actual, 1),
        "planned_to_date": round(planned_to_date, 1), "commissioned": round(commissioned, 1),
        "capacity": round(mw_all, 1), "last_cod": last_cod.strftime("%d-%b-%y") if last_cod else None,
        "charging": [sorted(((k, round(v, 1)) for k, v in d.items()), key=lambda kv: -kv[1]) for d in ftc],
        "blocks": blocks_all, "blocks_mw": blocks_mw,
    }


def fetch_pss_charging(db: Session, projects: List[Dict[str, Any]]) -> List[Optional[Dict[str, Any]]]:
    """Charging milestones the solar projects hold for each PSS, in date order."""
    ids = [p["obj"] for p in projects]
    out: List[Optional[Dict[str, Any]]] = []
    for label, pattern in PSS_ROWS:
        rows = db.execute(text("""
            SELECT baseline_finish_date, finish_date, actual_finish_date, status FROM p6_activity
            WHERE project_object_id = ANY(:ids) AND name ~* :pat
        """), {"ids": ids, "pat": pattern}).fetchall()
        if not rows:
            out.append(None)
            continue
        dates = sorted({((r[2] or r[1]).date() if (r[2] or r[1]) else None) for r in rows} - {None})
        base = min((r[0] for r in rows if r[0]), default=None)
        out.append({"label": label, "baseline": base.strftime("%d-%b-%y") if base else "-",
                    "charging": [d.strftime("%d-%b-%y") for d in dates[:3]], "n": len(dates)})
    return out


def fetch_robots(db: Session, projects: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
    """Robot count from the 'Robots - Construction' material: planned and installed."""
    row = db.execute(text("""
        SELECT SUM(planned_units), SUM(actual_units) FROM p6_resource_assignment
        WHERE project_object_id = ANY(:ids) AND resource_type = 'Material'
          AND resource_name = 'Robots - Construction'
    """), {"ids": [p["obj"] for p in projects]}).fetchone()
    if not row or not row[0]:
        return None
    return {"total": float(row[0]), "installed": float(row[1] or 0)}


def fetch_khavda_solar_progress(db: Session, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    projects = khavda_solar_projects(db)
    construction = fetch_construction(db, projects, today)
    return {
        "procurement": fetch_procurement(db, projects, today),
        "construction": construction,
        "manpower": fetch_manpower(db, projects, today, construction),
        "commissioning": fetch_commissioning(db, projects, today),
        "pss": fetch_pss_charging(db, projects),
        "robots": fetch_robots(db, projects),
        "n_projects": len(projects),
    }
