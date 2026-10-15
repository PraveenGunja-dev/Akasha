"""
Procurement and Construction Progress data for the Solar CPAG pack.

Everything here comes from P6 Material resource assignments, which carry real
quantities with a unit of measure:

  "<item> - Supply"        -> units received at site, per "Receipt at Site" lot
  "<item> - Construction"  -> units installed, per block

plus block-level activity status for the rows that are counted in blocks.

SAP is deliberately not used for quantities: mt_poamount's delivered quantity
equals its ordered quantity on every Bandha line (Modules read fully delivered
while P6 still has 3 of 4 lots pending) and its units (EA, MT, M) do not
convert to the pack's (MWp, Tables, km), so a figure from it would look
authoritative and be wrong.
"""
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

FORECAST_MONTHS = 3

# A supply row is shown only when P6's supply quantity agrees with its own
# construction quantity for the same item (HT Cable books 120 km of supply
# against 299 km to lay; Control Cable books 0 planned) - a disagreement means
# the receipt units are in a different basis and cannot be printed as a scope.
SUPPLY_RECONCILE_TOL = 0.10

# Template row order on the "Procurement" slide. `supply`/`construction` list
# P6 Material resource names; where several are given they are components of
# one deliverable (a MMS table needs rafter + purlin + bracing), so the row
# follows the component that is furthest behind. `wbs` is the P6 WBS holding
# the package's ordering milestones.
PROCUREMENT_ROWS: List[Dict[str, Any]] = [
    {"label": "Module", "wbs": "Module",
     "supply": ["Module - Supply"], "construction": ["Module - Construction"]},
    {"label": "MMS - FT", "wbs": "MMS - FT", "uom": "Tables",
     "supply": ["MMS - Rafter - Supply", "MMS - Purlin - Supply", "MMS - Bracing - Supply"],
     "construction": ["MMS - Rafter - Construction", "MMS - FT Purlin - Construction",
                      "MMS - Bracing - Construction"]},
    {"label": "IDT", "wbs": "IDT (incl. NIFPS)",
     "supply": ["IDT - Supply"], "construction": ["IDT - Construction"]},
    {"label": "Inverter", "wbs": "Inverter",
     "supply": ["Invertor - Supply"], "construction": ["Invertor - Construction"]},
    {"label": "HT Panel", "wbs": "HT Panel",
     "supply": ["HT Panel - Supply"], "construction": ["HT Panel - Construction"]},
    {"label": "LT Panel", "wbs": "LT Panel",
     "supply": ["LT Panel - Supply"], "construction": ["LT Panel - Construction"]},
    {"label": "HT Cable", "wbs": "HT Cable",
     "supply": ["HT Cable - Supply"], "construction": ["HT Cable - Construction"]},
    {"label": "LT Cable", "wbs": "LT Cable",
     "supply": ["LT Cable - Supply"], "construction": ["LT Cable - Construction"]},
    {"label": "Control Cable", "wbs": "Control Cables",
     "supply": ["Control Cable - Supply"], "construction": ["Control Cable - Construction"]},
    {"label": "DC Cable", "wbs": "DC Cable",
     "supply": ["DC Cable - Supply"], "construction": ["DC Cable - Construction"]},
    {"label": "Robotic Module Cleaning System",
     "wbs": "Robotic Cleaning System - Robots (incl Docking & Return Station)",
     "supply": ["Robots - Supply"], "construction": ["Robots - Construction"]},
]

# Template row order on the "Construction Progress" slide, from row 2.
# `material` rows are counted in installed units; `activity` rows in blocks
# (one activity per block); `mc4_voc` is MWdc, weighted by each block's module
# capacity. Rows with no entry (Piling, CEA, Commissioning) have no unit-level
# source in P6 - piles are not quantified, and block->MW (AC) is not recorded -
# so they stay "-" rather than be estimated.
CONSTRUCTION_ROWS: List[Optional[Dict[str, Any]]] = [
    None,  # Piling (Nos) - P6 does not quantify piles
    {"material": ["MMS - FT Purlin - Construction", "MMS - Rafter - Construction",
                  "MMS - Bracing - Construction"]},
    {"activity": "IDT Foundation up to rail"},
    {"activity": "HT & LT Station - Slab"},
    {"activity": "HT & LT Station - Shed Installation"},
    {"activity": "IDT Erection"},
    {"activity": "HT Panel Erection"},
    {"material": ["LT Panel - Construction"]},
    {"material": ["Invertor - Construction"]},
    {"material": ["LT Cable - Construction"]},
    {"material": ["HT Cable - Construction"]},
    {"material": ["Module - Construction"]},
    {"mc4_voc": True},
    None,  # CEA Inspection & Approval (MW) - block->MW is not recorded
    None,  # Commissioning & Trial Run (MW) - same
]

_BLOCK_PREFIX = re.compile(r"^block[\s-]*(\d+)\s*-\s*(.*)$", re.I)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _split_block(name: str):
    m = _BLOCK_PREFIX.match(name or "")
    return (m.group(1), _norm(m.group(2))) if m else (None, _norm(name))


def _slot(dt: Optional[datetime], first_fc: date) -> Optional[int]:
    """Forecast column for a finish date. Work P6 still shows open with a
    finish on or before the first forecast month (this month's lots, overdue
    lots on a schedule that has not been updated) lands in the first column;
    beyond the last column it is off the slide."""
    if dt is None:
        return None
    idx = (dt.year * 12 + dt.month) - (first_fc.year * 12 + first_fc.month)
    idx = max(idx, 0)
    return idx if idx < FORECAST_MONTHS else None


def _same_month(dt: Optional[datetime], ref: date) -> bool:
    return bool(dt) and dt.year == ref.year and dt.month == ref.month


def _first_forecast_month(today: date) -> date:
    y, m = divmod(today.year * 12 + today.month, 12)
    return date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)


def _month_actual_known(data_date: Optional[datetime], today: date) -> bool:
    """P6 has no actuals after its data date. When that is before this month
    began, 'actual this month' is unreported, not zero."""
    return bool(data_date) and (data_date.year, data_date.month) >= (today.year, today.month)


def _material_items(db: Session, obj_id: int) -> Dict[str, List[Dict[str, Any]]]:
    rows = db.execute(text("""
        SELECT ra.resource_name, ra.planned_units, ra.actual_units, ra.remaining_units,
               a.name, a.status, a.finish_date, a.actual_finish_date, a.baseline_finish_date
        FROM p6_resource_assignment ra
        JOIN p6_activity a ON a.p6_object_id = ra.activity_object_id
                          AND a.project_object_id = ra.project_object_id
        WHERE ra.project_object_id = :o AND ra.resource_type = 'Material'
    """), {"o": obj_id}).fetchall()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        planned, actual = float(r[1] or 0), float(r[2] or 0)
        remaining = float(r[3]) if r[3] is not None else max(planned - actual, 0.0)
        out.setdefault(r[0], []).append({
            "name": r[4], "planned": planned, "done": actual, "remaining": remaining,
            "completed": r[5] == "Completed", "finish": r[6],
            "actual_finish": r[7], "baseline_finish": r[8],
        })
    return out


def _binding(by_resource: Dict[str, List[Dict[str, Any]]], names: List[str]):
    """Of a deliverable's components, the one furthest behind (lowest done /
    planned). None when no component has any planned quantity."""
    best, best_ratio = None, None
    for n in names:
        items = by_resource.get(n)
        if not items:
            continue
        planned = sum(i["planned"] for i in items)
        if planned <= 0:
            continue
        ratio = sum(i["done"] for i in items) / planned
        if best is None or ratio < best_ratio:
            best, best_ratio = items, ratio
    return best


def _po_released(db: Session, obj_id: int, wbs: str) -> Optional[bool]:
    """Whether the package's 'LOI / PO Release' milestone is complete in P6.
    None when the package has no such milestone."""
    rows = db.execute(text("""
        SELECT status FROM p6_activity
        WHERE project_object_id = :o AND wbs_name = :w AND name ILIKE '%LOI / PO Release%'
    """), {"o": obj_id, "w": wbs}).fetchall()
    if not rows:
        return None
    return all(r[0] == "Completed" for r in rows)


def fetch_procurement_rows(db: Session, obj_id: int, today: Optional[date] = None) -> List[Optional[Dict[str, Any]]]:
    """One entry per template row of the Procurement slide; None where P6
    cannot support the row."""
    today = today or date.today()
    first_fc = _first_forecast_month(today)
    material = _material_items(db, obj_id)
    out: List[Optional[Dict[str, Any]]] = []
    for spec in PROCUREMENT_ROWS:
        supply = _binding(material, spec["supply"])
        cons = _binding(material, spec["construction"])
        if not supply:
            out.append(None)
            continue
        scope = sum(i["planned"] for i in supply)
        if cons:
            cons_scope = sum(i["planned"] for i in cons)
            if cons_scope <= 0 or abs(scope - cons_scope) / cons_scope > SUPPLY_RECONCILE_TOL:
                out.append(None)
                continue
        delivered = sum(i["done"] for i in supply)
        fc = [0.0] * FORECAST_MONTHS
        for i in supply:
            if i["completed"] or i["remaining"] <= 0:
                continue
            k = _slot(i["finish"], first_fc)
            if k is not None:
                fc[k] += i["remaining"]
        released = _po_released(db, obj_id, spec["wbs"])
        out.append({
            "uom": spec.get("uom"),
            "scope": scope,
            # Ordered = the whole package once P6 shows its PO release complete;
            # otherwise the quantity ordered is not known.
            "ordered": max(scope, delivered) if released else None,
            "balance": 0.0 if released else None,
            "delivered": delivered,
            "forecast": fc,
        })
    return out


def _activity_items(db: Session, obj_id: int) -> Dict[str, List[Dict[str, Any]]]:
    rows = db.execute(text("""
        SELECT name, status, finish_date, actual_finish_date, baseline_finish_date
        FROM p6_activity
        WHERE project_object_id = :o AND wbs_name ILIKE 'CONSTRUCTION%'
    """), {"o": obj_id}).fetchall()
    out: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        block, key = _split_block(r[0])
        out.setdefault(key, []).append({
            "block": block, "completed": r[1] == "Completed", "finish": r[2],
            "actual_finish": r[3], "baseline_finish": r[4],
        })
    return out


def _unit_items(items: List[Dict[str, Any]], qty_by_block: Optional[Dict[str, float]] = None
                ) -> List[Dict[str, Any]]:
    """Block activities as quantity items: 1 block each, or the block's own
    quantity where `qty_by_block` weights them."""
    out = []
    for i in items:
        q = qty_by_block.get(i["block"]) if qty_by_block is not None else 1.0
        if not q:
            continue
        out.append({
            "planned": q, "done": q if i["completed"] else 0.0,
            "remaining": 0.0 if i["completed"] else q, "completed": i["completed"],
            "finish": i["finish"], "actual_finish": i["actual_finish"],
            "baseline_finish": i["baseline_finish"],
        })
    return out


def _summarise(items: List[Dict[str, Any]], today: date, first_fc: date,
               actual_known: bool) -> Dict[str, Any]:
    fc = [0.0] * FORECAST_MONTHS
    for i in items:
        if i["completed"] or i["remaining"] <= 0:
            continue
        k = _slot(i["finish"], first_fc)
        if k is not None:
            fc[k] += i["remaining"]
    open_finishes = [i["finish"] for i in items if not i["completed"] and i["remaining"] > 0 and i["finish"]]
    return {
        "completed": sum(i["done"] for i in items),
        "month_plan": sum(i["planned"] for i in items if _same_month(i["baseline_finish"], today)),
        "month_actual": (sum(i["done"] for i in items if i["completed"] and _same_month(i["actual_finish"], today))
                         if actual_known else None),
        "forecast": fc,
        # Latest P6 forecast finish among open work; 'Completed' when none is open.
        "target": max(open_finishes).strftime("%d-%b-%y") if open_finishes else "Completed",
    }


def fetch_construction_rows(db: Session, obj_id: int, today: Optional[date] = None) -> List[Optional[Dict[str, Any]]]:
    """One entry per template row of the Construction Progress slide; None
    where P6 has no unit-level source."""
    today = today or date.today()
    first_fc = _first_forecast_month(today)
    dd = db.execute(text("SELECT data_date FROM p6_project WHERE p6_object_id = :o"), {"o": obj_id}).scalar()
    known = _month_actual_known(dd, today)
    material = _material_items(db, obj_id)
    acts = _activity_items(db, obj_id)

    module_by_block: Dict[str, float] = {}
    for i in material.get("Module - Construction", []):
        block, _ = _split_block(i["name"])
        if block:
            module_by_block[block] = module_by_block.get(block, 0.0) + i["planned"]

    out: List[Optional[Dict[str, Any]]] = []
    for spec in CONSTRUCTION_ROWS:
        items: Optional[List[Dict[str, Any]]] = None
        if spec and "material" in spec:
            items = _binding(material, spec["material"])
        elif spec and "activity" in spec:
            found = acts.get(_norm(spec["activity"]))
            items = _unit_items(found) if found else None
        elif spec and spec.get("mc4_voc"):
            # MC4 & VOC is done on a block only when both steps are.
            voc = acts.get("voc testing", [])
            mc4 = {i["block"]: i for i in acts.get("module interconnection & mc4 termination", [])}
            merged = [{**v, "completed": v["completed"] and bool(mc4.get(v["block"], {}).get("completed"))}
                      for v in voc if v["block"] in mc4]
            items = _unit_items(merged, module_by_block) if merged else None
        out.append(_summarise(items, today, first_fc, known) if items else None)
    return out
