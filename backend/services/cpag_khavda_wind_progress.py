"""
Procurement and Construction Progress tables of the Khavda Wind pack, from P6.

The Khavda wind projects are the P6 projects the register files under the Wind
cluster whose name carries a location count ("... PSS-12 (27 Loc.) & PSS-14 (60 Loc.)");
the register's other Wind rows (Mandvi, Mundra North) are other sites, and the
"Digital DPR - Demo" copy is not in the register.

Each component resource is booked twice in P6, so summing it double counts:
once on its "Ordering & Supply - ... - Delivery at Site" lots (the supply
quantity) and once on the erection / civil activity that installs it (the
construction quantity). Both are read separately here, by activity name.

Wind capacity in MW is held in neither P6 nor the register (the one Wind row
that carries a capacity is a solar-named plot), so no MW column is filled.
"""
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.cpag_solar_progress import (
    FORECAST_MONTHS, SUPPLY_RECONCILE_TOL, _first_forecast_month, _month_actual_known, _summarise,
)

SUPPLY_LOTS = "Ordering & Supply%"

# Template order of the Procurement page: (label, UOM, P6 resource, construction
# resource + activity pattern it must agree with).
PROCUREMENT_ROWS = [
    ("WTG Set (N-H-DT)", "Nos.", "WTG (NHDT)", ("WTG Erection", "%WTG Erection%")),
    ("Blade", "Nos.", "WTG (Blade)", ("WTG Erection", "%WTG Erection%")),
    ("Tower", "Nos.", "WTG (Tower)", ("WTG Erection", "%WTG Erection%")),
    ("Transformer", "Nos.", "USS Transformer", ("USS Erection", "%USS Erection%")),
    ("HT Panel", "Nos.", "USS HT Panel", ("USS Erection", "%USS Erection%")),
    ("33 kV / UG Cable", "Km", "HT Cable", ("HT Cable", "%Cable Laying%")),
]

# Template order of the Construction Progress page.
CONSTRUCTION_ROWS = [
    ("Stone Column", "Nos", "Stone Column", "%Stone Column%"),
    ("WTG Foundation", "Nos", "WTG Foundation", "%Raft Casting%"),
    ("USS Pre-cast Erection", "Nos", "USS Precast Installation", "%USS Precast Installation%"),
    ("WTG Erection", "Nos", "WTG Erection", "%WTG Erection%"),
    ("USS Erection", "Nos", "USS Erection", "%USS Erection%"),
    ("HT Cable Laying", "Km", "HT Cable", "%Cable Laying%"),
    ("WTG Commissioning (Trial Run)", "Nos", "WTG Commissioning", "%WTG Commissioning%"),
]


def khavda_wind_projects(db: Session) -> List[Dict[str, Any]]:
    rows = db.execute(text("""
        SELECT DISTINCT p6.p6_object_id, p6.name, p6.data_date, p6.baseline_finish_date,
                        p6.scheduled_finish_date, p6.duration_percent_complete
        FROM p6_project p6
        JOIN project_mapping pm ON p6.name = pm.project_name_from_p6
        WHERE pm.cluster = 'Wind' AND p6.name ~ 'Loc\\.'
          AND EXISTS (SELECT 1 FROM p6_activity a WHERE a.project_object_id = p6.p6_object_id LIMIT 1)
        ORDER BY p6.name
    """)).fetchall()
    return [{"obj": r[0], "name": r[1], "data_date": r[2], "baseline": r[3], "finish": r[4], "pct": r[5]}
            for r in rows]


def _items(db: Session, ids: List[int], resource: str, pattern: str, count: bool) -> List[Dict[str, Any]]:
    rows = db.execute(text("""
        SELECT ra.planned_units, ra.actual_units, ra.remaining_units, a.status, a.finish_date,
               a.actual_finish_date, a.baseline_finish_date
        FROM p6_resource_assignment ra
        JOIN p6_activity a ON a.p6_object_id = ra.activity_object_id
                          AND a.project_object_id = ra.project_object_id
        WHERE ra.project_object_id = ANY(:ids) AND ra.resource_type = 'Material'
          AND ra.resource_name = :res AND a.name ILIKE :pat
    """), {"ids": ids, "res": resource, "pat": pattern}).fetchall()
    out = []
    for planned, actual, remaining, status, finish, actual_finish, baseline in rows:
        planned, actual = float(planned or 0), float(actual or 0)
        completed = status == "Completed"
        # A unit is one location: a completed activity is fully done whatever
        # the posted quantity says; otherwise what has been posted, up to plan.
        done = (planned if completed else min(actual, planned)) if count else actual
        rem = float(remaining) if remaining is not None else max(planned - done, 0.0)
        out.append({"planned": planned, "done": done, "remaining": 0.0 if completed else rem,
                    "completed": completed, "finish": finish, "actual_finish": actual_finish,
                    "baseline_finish": baseline})
    return out


def _r(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(float(v), 2)


def fetch_wind_progress(db: Session, today: Optional[date] = None) -> Dict[str, Any]:
    today = today or date.today()
    first_fc = _first_forecast_month(today)
    projects = khavda_wind_projects(db)
    ids = [p["obj"] for p in projects]
    known = bool(projects) and all(_month_actual_known(p["data_date"], today) for p in projects)

    proc: List[Optional[Dict[str, Any]]] = []
    for label, uom, res, (c_res, c_pat) in PROCUREMENT_ROWS:
        supply = _items(db, ids, res, SUPPLY_LOTS, count=False)
        scope = sum(i["planned"] for i in supply)
        cons = sum(i["planned"] for i in _items(db, ids, c_res, c_pat, count=False))
        # Shown only where P6's supply quantity agrees with what is to be installed.
        if not supply or scope <= 0 or cons <= 0 or abs(scope - cons) / cons > SUPPLY_RECONCILE_TOL:
            proc.append(None)
            continue
        s = _summarise(supply, today, first_fc, known)
        delivered = sum(i["done"] for i in supply)
        proc.append({"label": label, "uom": uom, "scope": _r(scope), "delivered": _r(delivered),
                     "balance": _r(max(scope - delivered, 0.0)), "forecast": [_r(v) for v in s["forecast"]]})

    cons_rows: List[Optional[Dict[str, Any]]] = []
    for label, uom, res, pat in CONSTRUCTION_ROWS:
        items = _items(db, ids, res, pat, count=uom != "Km")
        if not items or sum(i["planned"] for i in items) <= 0:
            cons_rows.append(None)
            continue
        s = _summarise(items, today, first_fc, known)
        scope = sum(i["planned"] for i in items)
        cons_rows.append({"label": label, "uom": uom, "scope": _r(scope), "completed": _r(s["completed"]),
                          "balance": _r(max(scope - s["completed"], 0.0)),
                          "month_plan": _r(s["month_plan"]), "month_actual": _r(s["month_actual"]),
                          "forecast": [_r(v) for v in s["forecast"]], "target": s["target"]})

    locations = db.execute(text("""
        SELECT SUM(ra.planned_units) FROM p6_resource_assignment ra
        JOIN p6_activity a ON a.p6_object_id = ra.activity_object_id AND a.project_object_id = ra.project_object_id
        WHERE ra.project_object_id = ANY(:ids) AND ra.resource_type = 'Material'
          AND ra.resource_name = 'WTG Erection' AND a.name ILIKE '%WTG Erection%'
    """), {"ids": ids}).scalar()
    return {"projects": [p["name"] for p in projects], "n_projects": len(projects),
            "locations": int(locations or 0), "procurement": proc, "construction": cons_rows,
            "actual_known": known}
