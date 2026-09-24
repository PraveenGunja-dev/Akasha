"""
BESS / CPAG router.

Serves the CPAG monthly review pack for the six Khavda BESS projects, rebuilt
from live P6, SAP and Pulse data instead of the hand-maintained deck.

Sourcing notes (verified against the database, 2026-09-22):

* Progress is **units based**, not activity-count based.  Each BESS schedule
  carries one Nonlabor resource normalised to ~80,000,000 planned units = 100%,
  and rolling that up by WBS branch reproduces the pack's 2 / 5 / 38 / 55
  weightages exactly.  Counting completed activities instead reads the
  construction bucket roughly twice as high and must not be used here.
* SAP scope sits under **two** WBS prefixes per project - supply (H-5X../H-51X9)
  and civil (H-63..).  The civil family carries the BOP contractors and is the
  only SAP scope PSS-12 has.
* Capacity / energy / land figures have no system of record.  They are declared
  by the CPAG pack and are returned tagged with a source so the UI can label
  them; everything else on the screen is measured.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any, List, Optional
from collections import defaultdict
import re
import logging

from database import get_db
from services.cpag_pptx import build_project_pptx, build_portfolio_pptx

router = APIRouter(prefix="/api/bess")
logger = logging.getLogger(__name__)


# -- Project register --------------------------------------------------------
# supply_wbs / civil_wbs were established by matching the PO numbers printed in
# the CPAG pack against mt_poamount, then confirming that each civil prefix's
# vendor roster matches that project's contractor list in the pack.
BESS_PROJECTS: Dict[str, Dict[str, Any]] = {
    "AGE27BL_PSS11_FINAL": {
        "pss": "PSS-11", "spv": "AGE27BL", "plot": "S8+S9",
        "supply_wbs": "H-5XA1", "civil_wbs": "H-63A1",
        "power_mw": 1080, "energy_mwh": 2438, "dispatchable_mwh": 2211,
        "containers": 432, "land_acres": 69.1, "battery_oem": "CATL",
    },
    "AGE27CL_PSS12_FINAL": {
        "pss": "PSS-12", "spv": "AGE27CL", "plot": "S5+S6",
        "supply_wbs": None, "civil_wbs": "H-63A2",
        "power_mw": 960, "energy_mwh": 2167, "dispatchable_mwh": 1965,
        "containers": 384, "land_acres": 70.22, "battery_oem": "CATL",
    },
    "ARE35L_PSS10B_FINAL": {
        "pss": "PSS-10(B)", "spv": "ARE35L", "plot": "S13R",
        "supply_wbs": "H-51X9", "civil_wbs": "H-63X9",
        "power_mw": 600, "energy_mwh": 1204, "dispatchable_mwh": 1078,
        "containers": 240, "land_acres": 39.04, "battery_oem": "Jinko",
    },
    "AGE27AL_PSS09_FINAL": {
        "pss": "PSS-09", "spv": "AGE27AL", "plot": "A17",
        "supply_wbs": "H-5XWG", "civil_wbs": "H-63WG",
        "power_mw": 1080, "energy_mwh": 2438, "dispatchable_mwh": 2211,
        "containers": 432, "land_acres": 70.0, "battery_oem": "CATL",
    },
    "AGE44L_PSS5B_FINAL": {
        "pss": "PSS-05(B)", "spv": "AGE44L", "plot": "A17",
        "supply_wbs": "H-5XWD", "civil_wbs": "H-63WD",
        "power_mw": 1000, "energy_mwh": 2258, "dispatchable_mwh": 2041,
        "containers": 400, "land_acres": 68.81, "battery_oem": "CATL",
    },
    "AGE35L_PSS8B_FINAL": {
        "pss": "PSS-08(B)", "spv": "AGE35L", "plot": "A18",
        "supply_wbs": "H-5XWF", "civil_wbs": "H-63WF",
        "power_mw": 420, "energy_mwh": 843, "dispatchable_mwh": 758,
        "containers": 168, "land_acres": 31.3, "battery_oem": "GreatPower",
    },
}

# Approved NFA_R1 (04-Apr-26), from the CPAG pack's own capex table: Hard
# Cost 14,090 + Soft Cost 647 + Land Cost 1,190 + Contingency 431 = Rs 16,358
# Cr, across all six projects.  No system holds a month-by-month phasing of
# this figure, so the Financial S-Curve's Budgeted row spreads it across each
# project's own P6 baseline schedule, weighted by dispatchable MWh share -
# a schedule projection onto a real approved total, not a measurement.
TOTAL_NFA_CR = 16358.0
TOTAL_DISPATCHABLE_MWH = sum(c["dispatchable_mwh"] for c in BESS_PROJECTS.values())

# WBS branch code -> the CPAG pack's four weighted buckets.  Everything the map
# does not name (Project Milestones, HOTO, Contract Closure, Pre-Construction)
# belongs to the construction bucket - folding it in is what makes the weights
# land on 2 / 5 / 38 / 55 rather than 2 / 5 / 38 / 47.
BUCKETS = {
    "2": "statutory", "3": "engineering", "4": "procurement",
    "5": "construction", "6": "construction", "10": "construction",
    "11": "construction", "12": "construction",
}
BUCKET_ORDER = ["statutory", "engineering", "procurement", "construction"]
BUCKET_LABELS = {
    "statutory": "Statutory Approvals",
    "engineering": "Engineering",
    "procurement": "Ordering, Manufacturing & Supply",
    "construction": "Construction, Electrical, Integration & Commissioning",
}

# P6 package name -> SAP material_name, for joining the ordering plan to PO
# value.  Packages with no confident counterpart are left unmapped rather than
# guessed; the UI shows them with the SAP columns blank.
PACKAGE_SAP = {
    "Battery Container": "BESS Containers",
    "PCS": "PCS Supply",
    "Converter Transformer (CT) (Incl. NIFPS)": "IDT Transformer",
    "EMS": "EMS Supply",
    "HT Cables": "HT Cable",
    "MV Switchgear": "HT Panel",
    "SCADA Control Cable": "SCADA",
    # SAP books DC and LT cable on one material line, so only the DC package
    # carries the value - mapping both would count the same PO twice.
    "DC cable": "DC Cable & LT Cable",
}

# Superseded scope left in the schedule; it carries no live milestones.
PACKAGE_EXCLUDE = ("to be deleted",)


def _f(v) -> float:
    return float(v) if v is not None else 0.0


def _pct(num: float, den: float) -> Optional[float]:
    return round(num / den * 100, 2) if den else None


def _iso(d) -> Optional[str]:
    return d.isoformat() if d is not None else None


def _resolve(db: Session, project_id: str) -> Dict[str, Any]:
    cfg = BESS_PROJECTS.get(project_id)
    if not cfg:
        raise HTTPException(404, f"{project_id} is not a BESS project")
    row = db.execute(
        text("select p6_object_id, name, data_date, scheduled_finish_date, "
             "activity_count, completed_activity_count, in_progress_activity_count "
             "from p6_project where project_id = :p"),
        {"p": project_id},
    ).fetchone()
    if not row:
        raise HTTPException(404, f"No P6 schedule found for {project_id}")
    return {"cfg": cfg, "poid": row[0], "p6_name": row[1], "data_date": row[2],
            "scheduled_finish": row[3], "activity_count": row[4],
            "completed": row[5], "in_progress": row[6]}


def _wbs_roots(db: Session, poid: int) -> Dict[int, str]:
    """Map every WBS node to the code of its top-level branch."""
    rows = db.execute(
        text("select p6_object_id, parent_object_id, wbs_code "
             "from p6_wbs_node where project_object_id = :o"),
        {"o": poid},
    ).fetchall()
    by_id = {r[0]: r for r in rows}
    roots: Dict[int, str] = {}
    for node_id in by_id:
        cur, seen = node_id, set()
        while cur in by_id and by_id[cur][1] in by_id and cur not in seen:
            seen.add(cur)
            cur = by_id[cur][1]
        roots[node_id] = by_id[cur][2] if cur in by_id else ""
    return roots


# -- Endpoints ---------------------------------------------------------------
@router.get("/projects")
def list_bess_projects(db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """The six BESS projects that carry a CPAG pack."""
    out = []
    for pid, cfg in BESS_PROJECTS.items():
        exists = db.execute(
            text("select 1 from p6_project where project_id = :p"), {"p": pid}
        ).fetchone()
        out.append({"projectId": pid, "pss": cfg["pss"], "spv": cfg["spv"],
                    "hasSchedule": bool(exists)})
    return out


@router.get("/portfolio/cpag")
def get_portfolio_cpag(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """All six BESS projects together - the pack's portfolio view.

    Declared before /{project_id}/cpag so "portfolio" is not read as a project
    id.  Progress is rolled up **weighted by dispatchable energy**, not by a
    straight sum of weightage units: every schedule is normalised to the same
    ~80,000,000 units, so summing them would give a 420 MW project the same
    say as a 1,080 MW one.
    """
    projects: List[Dict[str, Any]] = []
    recv: Dict[str, float] = defaultdict(float)
    budget_series_list: List[List[Dict[str, Any]]] = []
    order_cr = delivered_cr = po_count = 0.0
    appr_total = appr_done = 0
    mandays_plan = mandays_earned = 0.0

    for pid, cfg in BESS_PROJECTS.items():
        row = db.execute(
            text("select p6_object_id from p6_project where project_id = :p"),
            {"p": pid},
        ).fetchone()
        if not row:
            continue
        poid = row[0]
        roots = _wbs_roots(db, poid)
        curve = _s_curve(db, poid)
        prog = _progress(db, poid, roots, curve["lastActualMonth"])
        appr = _approvals(db, poid, roots)
        man = _manpower(db, poid)
        comm = _commercial(db, cfg)
        proc = _procurement(db, poid, cfg)
        contractors = _contractors(db, cfg)
        engineering = _engineering(db, poid, roots)
        construction = _construction(db, poid, roots)
        electrical = _electrical(db, poid, roots)
        commissioning = _commissioning(db, poid)
        quality = _quality(db, cfg)

        plan_to_date = sum(b["planToDatePct"] or 0.0 for b in prog["buckets"])
        actual = prog["totalEarnedPct"] or 0.0
        weight = float(cfg["dispatchable_mwh"])

        projects.append({
            "projectId": pid, "pss": cfg["pss"], "spv": cfg["spv"],
            "powerMw": cfg["power_mw"], "energyMwh": cfg["energy_mwh"],
            "dispatchableMwh": cfg["dispatchable_mwh"],
            "containers": cfg["containers"], "batteryOem": cfg["battery_oem"],
            "planToDatePct": round(plan_to_date, 2),
            "actualPct": round(actual, 2),
            "variancePct": round(actual - plan_to_date, 2),
            "buckets": prog["buckets"],
            "approvalsTotal": appr["total"], "approvalsDone": appr["completed"],
            "orderCr": comm["orderCr"], "deliveredCr": comm["deliveredCr"],
            "sapAvailable": bool(cfg["supply_wbs"]),
            "lastActualMonth": curve["lastActualMonth"],
            # Each project keeps its own curve. The pack never blends progress
            # across projects - it gives each one its own slide - so these are
            # drawn as small multiples rather than averaged into one line.
            "sCurve": curve["series"],
            "approvals": appr["items"],
            "packages": proc["packages"],
            "servicePackages": proc.get("servicePackages") or [],
            "sap": proc["sap"],
            "sapNote": proc.get("sapNote"),
            "contractors": contractors["items"],
            "contractorNote": contractors["note"],
            "plot": cfg["plot"],
            "landAcres": cfg["land_acres"],
            "engineering": engineering,
            "construction": construction,
            "electrical": electrical,
            "commissioning": commissioning,
            "quality": quality,
            "manpower": man["series"],
        })


        for pt in comm["receiptSeries"]:
            recv[pt["month"]] += pt["monthCr"]
        budget_series_list.append(
            _budget_series(curve["series"], cfg["dispatchable_mwh"]))
        order_cr += comm["orderCr"]
        delivered_cr += comm["deliveredCr"]
        po_count += comm["poCount"]
        appr_total += appr["total"]
        appr_done += appr["completed"]
        mandays_plan += man["totalPlannedMandays"]
        mandays_earned += man["earnedMandays"]

    total_weight = sum(float(p["dispatchableMwh"]) for p in projects) or 1.0
    last_month = max((p["lastActualMonth"] for p in projects
                      if p["lastActualMonth"]), default=None)

    # No blended progress curve: the pack reports each project separately and
    # averaging six schedules that are each normalised to the same unit pool
    # would invent a number no one reviews.  Money is different - the pack does
    # total it - so the receipt series below is combined.
    cum, recv_series = 0.0, []
    for m in sorted(recv):
        cum += recv[m]
        recv_series.append({"month": m, "monthCr": round(recv[m], 2),
                            "cumCr": round(cum, 2)})

    weighted_actual = sum(p["actualPct"] * float(p["dispatchableMwh"])
                          for p in projects) / total_weight
    weighted_plan = sum(p["planToDatePct"] * float(p["dispatchableMwh"])
                        for p in projects) / total_weight

    return {
        "meta": {
            "projectCount": len(projects),
            "powerMw": sum(p["powerMw"] for p in projects),
            "energyMwh": sum(p["energyMwh"] for p in projects),
            "dispatchableMwh": sum(p["dispatchableMwh"] for p in projects),
            "containers": sum(p["containers"] for p in projects),
            "lastActualMonth": last_month,
            "declaredSource": "CPAG pack, 10-Sep-2026",
            "progressBasis": "Weighted by dispatchable MWh. Each P6 schedule is "
                             "normalised to the same unit pool, so an unweighted "
                             "sum would over-count the smaller projects. Shown as a "
                             "portfolio summary only - each project keeps its own curve.",
        },
        "projects": sorted(projects, key=lambda p: p["variancePct"]),
        "portfolioPlanPct": round(weighted_plan, 2),
        "portfolioActualPct": round(weighted_actual, 2),
        "portfolioVariancePct": round(weighted_actual - weighted_plan, 2),
        "commercial": {
            "poCount": int(po_count), "orderCr": round(order_cr, 2),
            "deliveredCr": round(delivered_cr, 2),
            "deliveredPct": _pct(delivered_cr, order_cr),
            "receiptSeries": recv_series,
        },
        "approvals": {"total": appr_total, "completed": appr_done},
        "manpower": {"totalPlannedMandays": round(mandays_plan),
                     "earnedMandays": round(mandays_earned),
                     "earnedPct": _pct(mandays_earned, mandays_plan),
                     "derived": True},
        "financial": _merge_financial(budget_series_list, recv_series),
    }


def _engineering(db: Session, poid: int, roots: Dict[int, str]) -> Dict[str, Any]:
    """Engineering activity progress from P6 WBS branch 3.

    The pack reports engineering as a document master log - total documents and
    approvals by category I-IV - which is not ingested.  What P6 does hold is
    the engineering *activities*, basic and detailed, with baseline and actual
    finish dates, so those are reported and the slide says which it is.
    """
    ids = [k for k, v in roots.items() if v == "3"]
    if not ids:
        return {"groups": [], "items": [], "total": 0, "completed": 0,
                "monthly": [], "basis": ""}
    rows = db.execute(
        text("""select a.wbs_name, a.name, a.status, a.baseline_finish_date,
                       a.actual_finish_date, a.finish_date
                from p6_activity a where a.wbs_object_id = any(:w)
                order by a.baseline_finish_date nulls last"""),
        {"w": ids},
    ).fetchall()
    items = [{
        "group": r[0], "name": r[1], "status": r[2],
        "baselineFinish": _iso(r[3]), "actualFinish": _iso(r[4]),
        "forecastFinish": _iso(r[5]),
        "slipDays": (r[4] - r[3]).days if r[3] and r[4] else None,
    } for r in rows]

    groups: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
    plan_m: Dict[str, int] = defaultdict(int)
    act_m: Dict[str, int] = defaultdict(int)
    for it in items:
        g = groups[it["group"] or "Engineering"]
        g[0] += 1
        if it["status"] == "Completed":
            g[1] += 1
        if it["baselineFinish"]:
            plan_m[it["baselineFinish"][:7]] += 1
        if it["actualFinish"]:
            act_m[it["actualFinish"][:7]] += 1

    months = sorted(set(plan_m) | set(act_m))
    cp = ca = 0
    monthly = []
    for m in months:
        cp += plan_m[m]
        ca += act_m[m]
        monthly.append({"month": m, "planMonth": plan_m[m], "planCum": cp,
                        "actualMonth": act_m[m], "actualCum": ca})
    return {
        "groups": [{"name": k, "total": v[0], "completed": v[1],
                    "pct": _pct(v[1], v[0])} for k, v in sorted(groups.items())],
        "items": items, "total": len(items),
        "completed": sum(1 for i in items if i["status"] == "Completed"),
        "monthly": monthly,
        "basis": "P6 engineering activities, basic and detailed. The pack's "
                 "document master log - total documents and Cat I-IV approvals "
                 "- is not ingested.",
    }


def _commissioning(db: Session, poid: int) -> Dict[str, Any]:
    """Commissioning and trial-run phases from P6.

    The pack schedules commissioning as MWh and container count per month.  P6
    holds the phase milestones and their dates but not the energy released in
    each month, so the phases are reported with baseline against forecast.
    """
    rows = db.execute(
        text("""select name, status, baseline_finish_date, actual_finish_date,
                       finish_date
                from p6_activity
                where project_object_id = :o
                  and (name ilike :comm or name ilike :proj or name ilike :trial)
                order by coalesce(actual_finish_date, finish_date)"""),
        {"o": poid, "comm": "%commissioning phase%",
         "proj": "%project commissioning%", "trial": "%trial run%"},
    ).fetchall()
    items = [{
        "name": r[0], "status": r[1], "baselineFinish": _iso(r[2]),
        "actualFinish": _iso(r[3]), "forecastFinish": _iso(r[4]),
        "slipDays": (r[4] - r[2]).days if r[2] and r[4] else None,
    } for r in rows]

    by_month: Dict[str, int] = defaultdict(int)
    for it in items:
        d = it["actualFinish"] or it["forecastFinish"]
        if d:
            by_month[d[:7]] += 1
    return {"items": items,
            "monthly": [{"month": m, "milestones": n}
                        for m, n in sorted(by_month.items())],
            "total": len(items),
            "completed": sum(1 for i in items if i["status"] == "Completed"),
            "basis": "P6 commissioning and trial-run milestones. The pack's "
                     "month-by-month MWh and container release has no source."}


def _quality(db: Session, cfg) -> Dict[str, Any]:
    """Pulse inspection and non-conformance record for this project."""
    name = "BESS %s Project" % cfg["pss"].replace("(", "").replace(")", "")
    nc_status = [{"status": r[0] or "Unknown", "count": r[1]} for r in db.execute(
        text("select status_label, count(*) from pulse_nc "
             "where project_name = :p group by 1 order by 2 desc"), {"p": name})]
    rfi_pkg = [{"package": r[0] or "Unknown", "count": r[1]} for r in db.execute(
        text("select package_name, count(*) from pulse_rfi "
             "where project_name = :p group by 1 order by 2 desc"), {"p": name})]
    monthly = [{"month": r[0], "rfi": r[1]} for r in db.execute(
        text("select to_char(created_at,'YYYY-MM'), count(*) from pulse_rfi "
             "where project_name = :p and created_at is not null "
             "group by 1 order by 1"), {"p": name})]
    nc_monthly = {r[0]: r[1] for r in db.execute(
        text("select to_char(created_at,'YYYY-MM'), count(*) from pulse_nc "
             "where project_name = :p and created_at is not null group by 1"),
        {"p": name})}
    for m in monthly:
        m["nc"] = nc_monthly.get(m["month"], 0)
    rfi_total = sum(r["count"] for r in rfi_pkg)
    nc_total = sum(r["count"] for r in nc_status)
    return {"project": name, "rfiTotal": rfi_total, "ncTotal": nc_total,
            "ncRatePct": _pct(nc_total, rfi_total),
            "ncByStatus": nc_status, "rfiByPackage": rfi_pkg,
            "monthly": monthly,
            "openNc": sum(r["count"] for r in nc_status
                          if r["status"] not in ("Approved", "Rejected"))}


# Construction and commissioning branches - the only ones whose Material
# assignments are installed quantity rather than delivered quantity.
CONSTRUCTION_BRANCHES = {"5", "6", "10", "11", "12"}


def _construction(db: Session, poid: int, roots: Dict[int, str]) -> Dict[str, Any]:
    """Element-by-stage physical progress from P6 Material resources.

    The Civil slide and the Electrical slide draw on the same Material pool
    (both are "installed quantity" work under the Construction WBS branches).
    Resources already reported on the Electrical slide (`ELECTRICAL_ELEMENTS`)
    are excluded here so a cable-laying or erection quantity is never counted
    on both slides as if it were two different pieces of work.
    """
    ids = [k for k, v in roots.items() if v in CONSTRUCTION_BRANCHES]
    if not ids:
        return {"elements": [], "basis": ""}
    electrical_resources = {resource for _label, resource, _uom in ELECTRICAL_ELEMENTS}
    rows = db.execute(
        text("""select r.resource_name, sum(r.planned_units), sum(r.actual_units)
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                where r.project_object_id = :o and r.resource_type = 'Material'
                  and a.wbs_object_id = any(:w)
                group by 1 having sum(r.planned_units) > 0
                order by 2 desc"""),
        {"o": poid, "w": ids},
    ).fetchall()

    # Names follow "ELEMENT - Stage"; anything without that prefix is a stage
    # in its own right and is grouped under General.
    elements: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for name, planned, actual in rows:
        if name in electrical_resources:
            continue
        pl, ac = _f(planned), _f(actual)
        if " - " in name:
            element, stage = name.split(" - ", 1)
        else:
            element, stage = "General", name
        elements[element.strip()].append({
            "stage": stage.strip(), "planned": round(pl), "actual": round(ac),
            "pct": _pct(ac, pl),
        })

    out = []
    for element, stages in elements.items():
        pl = sum(s["planned"] for s in stages)
        ac = sum(s["actual"] for s in stages)
        out.append({
            "element": element, "stages": stages,
            "planned": pl, "actual": ac, "pct": _pct(ac, pl),
            "stageCount": len(stages),
        })
    # Largest scope first - the elements that carry the schedule lead.
    out.sort(key=lambda e: -e["planned"])
    return {
        "elements": out,
        "basis": "P6 Material resource assignments on Construction and "
                 "Commissioning activities. Unit bases differ from the pack "
                 "(P6 counts piles where the pack counts foundations), so "
                 "percentages are reported rather than the pack's counts.",
    }


# Pack label -> P6 Material resource, confirmed by matching scope. Anything not
# named here keeps its P6 resource name rather than being forced onto a pack
# label it may not be.
ELECTRICAL_ELEMENTS = [
    ("HT Cable Laying", "HT - Cable Laying", "RM"),
    ("FO Cable Laying", "PPC - FO Cable", "RM"),
    ("DC Cable Laying", "DC - Support erection", "RM"),
    ("LT Cable Laying", "AC - Support erection", "RM"),
    ("Aux Cable Laying", "AUX - LT Cable Laying", "RM"),
    ("Control Cable Laying", "AUX - Control cable laying", "RM"),
    ("Battery Container Erection", "Container Erection", "NOS"),
    ("PCS Erection", "PCS Erection", "NOS"),
    ("CT Erection", "Converter Transformer Erection", "NOS"),
    ("CSS Erection", "CSS - CSS Erection", "NOS"),
    ("SGR HT Panel Erection", "SGR - HT Panel erection", "NOS"),
    ("NIFPS Erection", "NIFPS - NIFPS Erection", "NOS"),
]


def _electrical(db: Session, poid: int, roots: Dict[int, str]) -> Dict[str, Any]:
    """Element-level electrical progress, on the pack's own row labels.

    Fetches its own data date from the project rather than trusting a caller
    to pass one, so the single-project and portfolio call sites can never
    disagree on what "today" is for this slide.
    """
    ids = [k for k, v in roots.items() if v in CONSTRUCTION_BRANCHES]
    if not ids:
        return {"items": [], "basis": ""}
    data_date = db.execute(
        text("select data_date from p6_project where p6_object_id = :o"),
        {"o": poid},
    ).scalar()
    rows = db.execute(
        text("""select r.resource_name, sum(r.planned_units), sum(r.actual_units)
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                where r.project_object_id = :o and r.resource_type = 'Material'
                  and a.wbs_object_id = any(:w)
                group by 1 having sum(r.planned_units) > 0"""),
        {"o": poid, "w": ids},
    ).fetchall()
    by_name = {r[0]: (_f(r[1]), _f(r[2])) for r in rows}

    items = []
    for label, resource, uom in ELECTRICAL_ELEMENTS:
        if resource not in by_name:
            continue
        scope, actual = by_name[resource]
        items.append({
            "element": label, "resource": resource, "uom": uom,
            # The pack prints both a "Scope" and a "Plan" column holding the
            # same figure (plan is the full scope, phased flat since P6 holds
            # no dated quantity curve) - reproduced as two columns to match.
            "scope": round(scope), "plan": round(scope), "actual": round(actual),
            "actualPct": _pct(actual, scope),
            "planPct": 100.0,
        })
    return {
        "items": items,
        "dataDate": _iso(data_date),
        "basis": "P6 Material resources on Construction activities. Scope "
                 "reconciles with the pack; actuals may read differently "
                 "because the pack is FTM 10-Sep-26 and this is P6's data "
                 "date. Plan is full scope - P6 holds no dated quantity "
                 "curve to phase it.",
    }


@router.get("/portfolio/cpag.pptx")
def download_portfolio_pptx(db: Session = Depends(get_db)) -> Response:
    """The portfolio pack as a PowerPoint file, built from the same payload."""
    data = get_portfolio_cpag(db)
    return Response(
        content=build_portfolio_pptx(data),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition":
                 'attachment; filename="CPAG_BESS_Portfolio.pptx"'},
    )


@router.get("/{project_id}/cpag.pptx")
def download_project_pptx(project_id: str, db: Session = Depends(get_db)) -> Response:
    """One project's pack as a PowerPoint file."""
    data = get_cpag(project_id, db)
    safe = data["meta"]["pss"].replace("(", "").replace(")", "").replace(" ", "_")
    return Response(
        content=build_project_pptx(data),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="CPAG_{safe}.pptx"'},
    )


@router.get("/{project_id}/cpag")
def get_cpag(project_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ctx = _resolve(db, project_id)
    cfg, poid = ctx["cfg"], ctx["poid"]
    roots = _wbs_roots(db, poid)

    curve = _s_curve(db, poid)
    comm = _commercial(db, cfg)
    budget = _budget_series(curve["series"], cfg["dispatchable_mwh"])
    return {
        "meta": _meta(ctx),
        "progress": _progress(db, poid, roots, curve["lastActualMonth"]),
        "sCurve": curve,
        "procurement": _procurement(db, poid, cfg),
        "approvals": _approvals(db, poid, roots),
        "engineering": _engineering(db, poid, roots),
        "construction": _construction(db, poid, roots),
        "electrical": _electrical(db, poid, roots),
        "commissioning": _commissioning(db, poid),
        "quality": _quality(db, cfg),
        "manpower": _manpower(db, poid),
        "contractors": _contractors(db, cfg),
        "commercial": comm,
        "financial": _merge_financial([budget], comm["receiptSeries"]),
    }


def _meta(ctx) -> Dict[str, Any]:
    cfg = ctx["cfg"]
    return {
        "pss": cfg["pss"], "spv": cfg["spv"], "plot": cfg["plot"],
        "p6Name": ctx["p6_name"],
        "dataDate": _iso(ctx["data_date"]),
        "scheduledFinish": _iso(ctx["scheduled_finish"]),
        "activityCount": ctx["activity_count"],
        "completedActivities": ctx["completed"],
        "inProgressActivities": ctx["in_progress"],
        "supplyWbs": cfg["supply_wbs"], "civilWbs": cfg["civil_wbs"],
        # Declared by the CPAG pack - no system of record. Tagged so the UI
        # can mark it rather than passing it off as measured.
        "declared": {
            "powerMw": cfg["power_mw"], "energyMwh": cfg["energy_mwh"],
            "dispatchableMwh": cfg["dispatchable_mwh"],
            "containers": cfg["containers"], "landAcres": cfg["land_acres"],
            "batteryOem": cfg["battery_oem"],
            "source": "CPAG pack, 10-Sep-2026",
        },
    }


def _progress(db: Session, poid: int, roots: Dict[int, str],
              as_of: Optional[str] = None) -> Dict[str, Any]:
    """Weighted progress from the Nonlabor weightage resource.

    `as_of` is the last month with reported actuals.  Planned units whose
    baseline finish falls on or before it are the bucket's plan-to-date, which
    is what the pack prints beside actual as "Plan vs Actual".
    """
    rows = db.execute(
        text("""select a.wbs_object_id, sum(r.planned_units), sum(r.actual_units),
                       sum(case when to_char(a.baseline_finish_date,'YYYY-MM') <= :m
                                then r.planned_units else 0 end)
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                where r.project_object_id = :o and r.resource_type = 'Nonlabor'
                group by 1"""),
        {"o": poid, "m": as_of or "9999-99"},
    ).fetchall()
    agg: Dict[str, List[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for wbs_id, planned, actual, to_date in rows:
        b = BUCKETS.get(roots.get(wbs_id, ""), "construction")
        agg[b][0] += _f(planned)
        agg[b][1] += _f(actual)
        agg[b][2] += _f(to_date)

    total = sum(v[0] for v in agg.values())
    buckets = []
    for key in BUCKET_ORDER:
        planned, actual, to_date = agg.get(key, [0.0, 0.0, 0.0])
        plan_pct, earned_pct = _pct(to_date, total), _pct(actual, total)
        buckets.append({
            "key": key, "label": BUCKET_LABELS[key],
            "weightPct": _pct(planned, total),
            "planToDatePct": plan_pct,
            "earnedPct": earned_pct,
            "variancePct": (round(earned_pct - plan_pct, 2)
                            if plan_pct is not None and earned_pct is not None else None),
            "withinBucketPct": _pct(actual, planned),
            "plannedUnits": round(planned), "actualUnits": round(actual),
        })
    earned = sum(v[1] for v in agg.values())
    return {"buckets": buckets, "totalPlannedUnits": round(total),
            "totalEarnedPct": _pct(earned, total),
            "basis": "P6 Nonlabor weightage units (planned vs actual)"}


def _s_curve(db: Session, poid: int) -> Dict[str, Any]:
    """Planned curve phased on baseline finish, actual on actual finish."""
    rows = db.execute(
        text("""select to_char(a.baseline_finish_date,'YYYY-MM') bm,
                       to_char(a.actual_finish_date,'YYYY-MM') am,
                       sum(r.planned_units), sum(r.actual_units)
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                where r.project_object_id = :o and r.resource_type = 'Nonlabor'
                group by 1, 2"""),
        {"o": poid},
    ).fetchall()
    total = sum(_f(r[2]) for r in rows)
    plan_m: Dict[str, float] = defaultdict(float)
    act_m: Dict[str, float] = defaultdict(float)
    for bm, am, planned, actual in rows:
        if bm:
            plan_m[bm] += _f(planned)
        if am:
            act_m[am] += _f(actual)

    months = sorted(set(plan_m) | set(act_m))
    series, cum_p, cum_a = [], 0.0, 0.0
    last_actual = max(act_m) if act_m else None
    for m in months:
        cum_p += plan_m[m]
        cum_a += act_m[m]
        reported = bool(last_actual) and m <= last_actual
        series.append({
            "month": m,
            "planMonthPct": _pct(plan_m[m], total),
            "planCumPct": _pct(cum_p, total),
            # The actual curve must stop at the last month with postings -
            # carrying a flat line past it would read as "no progress" rather
            # than "not yet reported".
            "actualMonthPct": _pct(act_m[m], total) if reported else None,
            "actualCumPct": _pct(cum_a, total) if reported else None,
        })
    return {"series": series, "lastActualMonth": last_actual,
            "totalUnits": round(total)}


def _wbs_children_as_packages(db: Session, poid: int, wbs_name: str
                              ) -> List[Dict[str, Any]]:
    """Every activity under one named WBS node's direct children, shaped as
    the pack's package rows. Used for both "Ordering & Delivery" (supply) and
    "Service Order" (service) - two sibling branches under Procurement that
    the pack reports on separate slides, so both get pulled the same way
    rather than only the one branch a single query happened to reach.
    """
    parent = db.execute(
        text("""select p6_object_id from p6_wbs_node
                where project_object_id = :o and wbs_name = :n"""),
        {"o": poid, "n": wbs_name},
    ).fetchone()
    if not parent:
        return []
    nodes = db.execute(
        text("""select p6_object_id, wbs_name from p6_wbs_node
                where project_object_id = :o and parent_object_id = :p
                order by wbs_name"""),
        {"o": poid, "p": parent[0]},
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for node_id, name in nodes:
        # Every activity attached to this WBS node - not a named subset of
        # milestones - so a tracking step added under a package is picked up
        # without the mapping needing to name it.
        acts = db.execute(
            text("""select name, status, baseline_finish_date,
                           actual_finish_date, finish_date
                    from p6_activity where wbs_object_id = :w
                    order by baseline_start_date nulls last"""),
            {"w": node_id},
        ).fetchall()
        if not acts:
            continue
        if any(t in name.lower() for t in PACKAGE_EXCLUDE):
            continue
        base = re.sub(r"\s*-\s*[\d,]+\s*(nos|set|sets|kms|km)\.?\s*$", "",
                      name, flags=re.I).strip()
        qty = None
        m = re.search(r"-\s*([\d,]+)\s*(nos|set|sets|kms|km)", name, re.I)
        if m:
            qty = int(m.group(1).replace(",", ""))
        out.append({
            "package": name, "packageBase": base, "scopeQty": qty,
            "sapMaterial": PACKAGE_SAP.get(base),
            "milestones": [{
                "name": a[0], "status": a[1],
                "baselineFinish": _iso(a[2]), "actualFinish": _iso(a[3]),
                "forecastFinish": _iso(a[4]),
                "slipDays": (a[3] - a[2]).days if a[2] and a[3] else None,
            } for a in acts],
        })
    return out


def _procurement(db: Session, poid: int, cfg) -> Dict[str, Any]:
    """Ordering and delivery activities per package, joined to SAP PO value.

    "Ordering & Delivery" and "Service Order" are sibling WBS branches under
    Procurement - the pack reports them as two different slide families
    (Supply / Service ordering status), so both are pulled here rather than
    only the supply side.
    """
    packages = _wbs_children_as_packages(db, poid, "Ordering & Delivery")
    service_packages = _wbs_children_as_packages(db, poid, "Service Order")

    # SAP side, supply prefix only - the civil prefix carries services.
    sap_rows: List[Any] = []
    if cfg["supply_wbs"]:
        sap_rows = db.execute(
            text("""select material_name, max(vendor_name),
                           count(distinct purchasing_document),
                           string_agg(distinct purchasing_document, ', '),
                           sum(net_order_value_inr)/1e7,
                           sum(delivered_value_inr_cr),
                           sum(po_quantities), sum(delivered_qty)
                    from mt_poamount
                    where left(wbs_element,6) = :w and doc_type = 'POrd'
                    group by 1 order by 5 desc"""),
            {"w": cfg["supply_wbs"]},
        ).fetchall()
    sap = [{
        "material": r[0], "vendor": r[1], "poCount": r[2], "poNumbers": r[3],
        "orderCr": round(_f(r[4]), 2), "deliveredCr": round(_f(r[5]), 2),
        # Quantities across multi-line POs do not reconcile and mix units of
        # measure, so they are returned for reference but never charted.
        "orderQtyRaw": _f(r[6]), "deliveredQtyRaw": _f(r[7]),
    } for r in sap_rows]

    note = None
    if not cfg["supply_wbs"]:
        note = ("Supply POs for this project are not present in the current "
                "ZPSPS007 extract. Civil scope is available under "
                f"{cfg['civil_wbs']}.")
    return {"packages": packages, "servicePackages": service_packages,
            "sap": sap, "sapAvailable": bool(cfg["supply_wbs"]), "sapNote": note}


def _approvals(db: Session, poid: int, roots: Dict[int, str]) -> Dict[str, Any]:
    ids = [k for k, v in roots.items() if v == "2"]
    if not ids:
        return {"items": [], "total": 0, "completed": 0, "inProgress": 0}
    rows = db.execute(
        text("""select name, status, baseline_start_date, baseline_finish_date,
                       actual_start_date, actual_finish_date, finish_date
                from p6_activity where wbs_object_id = any(:w)
                order by baseline_start_date nulls last"""),
        {"w": ids},
    ).fetchall()
    items = [{
        "name": r[0], "status": r[1],
        "baselineStart": _iso(r[2]), "baselineFinish": _iso(r[3]),
        "actualStart": _iso(r[4]), "actualFinish": _iso(r[5]),
        "forecastFinish": _iso(r[6]),
        "slipDays": (r[5] - r[3]).days if r[3] and r[5] else None,
    } for r in rows]
    return {"items": items, "total": len(items),
            "completed": sum(1 for i in items if i["status"] == "Completed"),
            "inProgress": sum(1 for i in items if i["status"] == "In Progress")}


def _manpower(db: Session, poid: int) -> Dict[str, Any]:
    """Planned mandays from Labor units; earned = planned x percent complete.

    Actual labour units are not posted in P6 (1 non-zero row in 3,104 on
    PSS-11), so the actual series is *earned* mandays - mandays credited for
    work done, the manday analogue of earned value.  It is flagged derived
    because it cannot show a productivity gap: by construction earned/planned
    equals physical progress.
    """
    rows = db.execute(
        text("""select to_char(a.baseline_finish_date,'YYYY-MM') bm,
                       to_char(coalesce(a.actual_finish_date, p.data_date),'YYYY-MM') am,
                       sum(r.planned_units),
                       sum(r.planned_units * coalesce(a.percent_complete, 0)),
                       sum(r.actual_units)
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                join p6_project p on p.p6_object_id = r.project_object_id
                where r.project_object_id = :o and r.resource_type = 'Labor'
                group by 1, 2"""),
        {"o": poid},
    ).fetchall()
    total = sum(_f(r[2]) for r in rows)
    posted = sum(_f(r[4]) for r in rows)
    plan_m: Dict[str, float] = defaultdict(float)
    earn_m: Dict[str, float] = defaultdict(float)
    for bm, am, planned, earned, _posted in rows:
        if bm:
            plan_m[bm] += _f(planned)
        if am:
            earn_m[am] += _f(earned)

    months = sorted(set(plan_m) | set(earn_m))
    series, cp, ce = [], 0.0, 0.0
    for m in months:
        cp += plan_m[m]
        ce += earn_m[m]
        series.append({"month": m, "planMonth": round(plan_m[m]),
                       "planCum": round(cp), "earnedMonth": round(earn_m[m]),
                       "earnedCum": round(ce), "earnedPct": _pct(ce, total)})
    return {"series": series, "totalPlannedMandays": round(total),
            "earnedMandays": round(ce), "postedActualUnits": round(posted),
            "derived": True,
            "basis": "Earned mandays = planned Labor units x activity percent "
                     "complete. Actual labour units are not posted in P6."}


def _contractors(db: Session, cfg) -> Dict[str, Any]:
    """Contractor scope and delivery from SAP, quality from Pulse.

    The CPAG pack reports contractor *headcount* by month (forecast / actual /
    shortfall).  No connected system holds that, so this returns what is
    measured: contracted value, delivered value and quality record counts.
    """
    prefixes = [p for p in (cfg["supply_wbs"], cfg["civil_wbs"]) if p]
    rows = db.execute(
        text("""select vendor_name,
                       count(distinct purchasing_document),
                       sum(net_order_value_inr)/1e7,
                       sum(delivered_value_inr_cr),
                       string_agg(distinct material_name, ', '),
                       string_agg(distinct left(wbs_element,6), ',')
                from mt_poamount
                where left(wbs_element,6) = any(:p) and doc_type = 'POrd'
                group by 1 order by 3 desc"""),
        {"p": prefixes},
    ).fetchall()
    pulse_name = "BESS %s Project" % cfg["pss"].replace("(", "").replace(")", "")
    rfi = {r[0]: r[1] for r in db.execute(
        text("select vendor_name, count(*) from pulse_rfi "
             "where project_name = :p group by 1"), {"p": pulse_name}).fetchall()}
    nc = {r[0]: r[1] for r in db.execute(
        text("select vendor_name, count(*) from pulse_nc "
             "where project_name = :p group by 1"), {"p": pulse_name}).fetchall()}

    items = []
    for vendor, pos, order_cr, del_cr, mats, wbs_list in rows:
        o, d = round(_f(order_cr), 2), round(_f(del_cr), 2)
        on_civil = bool(cfg["civil_wbs"] and cfg["civil_wbs"] in (wbs_list or ""))
        r_n, n_n = rfi.get(vendor, 0), nc.get(vendor, 0)
        items.append({
            "vendor": vendor, "poCount": pos, "orderCr": o, "deliveredCr": d,
            "deliveredPct": _pct(d, o), "scope": mats,
            # Site contractors are the firms working on the civil/erection
            # scope - they are the ones the pack's manpower slides track.
            # Everyone else is a supply OEM and has no Pulse footprint.
            "kind": "site" if (on_civil or r_n or n_n) else "supply",
            "rfiCount": r_n, "ncCount": n_n,
            "ncRatePct": _pct(n_n, r_n),
        })
    return {"items": items, "pulseProject": pulse_name,
            "siteCount": sum(1 for i in items if i["kind"] == "site"),
            "headcountAvailable": False,
            "note": "Monthly contractor headcount (forecast / actual / shortfall) "
                    "is not held in any connected system. Contracted and delivered "
                    "value, and Pulse quality records, are shown instead."}


def _budget_series(curve_series: List[Dict[str, Any]],
                   dispatchable_mwh: float) -> List[Dict[str, Any]]:
    """This project's derived share of the approved NFA (TOTAL_NFA_CR above),
    phased on its own P6 baseline plan curve rather than a cost-loaded
    schedule no connected system holds."""
    share_cr = TOTAL_NFA_CR * (float(dispatchable_mwh) / TOTAL_DISPATCHABLE_MWH)
    out, prev = [], 0.0
    for pt in curve_series:
        plan_pct = pt.get("planCumPct")
        if plan_pct is None:
            continue
        cum = share_cr * (plan_pct / 100.0)
        out.append({"month": pt["month"], "cumCr": round(cum, 2),
                    "monthCr": round(cum - prev, 2)})
        prev = cum
    return out


def _merge_financial(budget_series_list: List[List[Dict[str, Any]]],
                     receipt_series: List[Dict[str, Any]]) -> Dict[str, Any]:
    """One or more projects' derived budget curves, and the (already
    combined) receipt curve, onto a single month axis - the pack's own
    Financial S-Curve table: Budgeted cumulative / Monthly Budgeted / Actual
    Cumulative / Monthly Actual, one column per month."""
    months = sorted(
        {pt["month"] for series in budget_series_list for pt in series}
        | {pt["month"] for pt in receipt_series}
    )
    budget_by_month: Dict[str, float] = defaultdict(float)
    for series in budget_series_list:
        by_month = {pt["month"]: pt["cumCr"] for pt in series}
        carried = 0.0
        for m in months:
            if m in by_month:
                carried = by_month[m]
            budget_by_month[m] += carried

    receipt_cum = {pt["month"]: pt["cumCr"] for pt in receipt_series}
    rows, prev_b, carried_a = [], 0.0, 0.0
    for m in months:
        b = budget_by_month.get(m, prev_b)
        if m in receipt_cum:
            carried_a = receipt_cum[m]
        rows.append({
            "month": m,
            "budgetedCumCr": round(b, 2),
            "budgetedMonthCr": round(b - prev_b, 2),
            "actualCumCr": round(carried_a, 2),
            "actualMonthCr": round(carried_a - (rows[-1]["actualCumCr"] if rows else 0.0), 2),
        })
        prev_b = b
    return {"series": rows}


def _commercial(db: Session, cfg) -> Dict[str, Any]:
    """Order book and monthly received value across both WBS families."""
    prefixes = [p for p in (cfg["supply_wbs"], cfg["civil_wbs"]) if p]
    totals = db.execute(
        text("""select count(distinct purchasing_document),
                       sum(net_order_value_inr)/1e7,
                       sum(delivered_value_inr_cr)
                from mt_poamount
                where left(wbs_element,6) = any(:p) and doc_type = 'POrd'"""),
        {"p": prefixes},
    ).fetchone()
    # Goods-receipt postings carry a credit sign convention; the magnitude is
    # the value received, so it is normalised here.
    rows = db.execute(
        text("""select to_char(posting_date,'YYYY-MM') m,
                       sum(abs(coalesce(amount_in_lc_cr, 0)))
                from mt_materialdocument
                where left(wbs_element,6) = any(:p) and posting_date is not null
                group by 1 order by 1"""),
        {"p": prefixes},
    ).fetchall()
    series, cum = [], 0.0
    for m, v in rows:
        cum += _f(v)
        series.append({"month": m, "monthCr": round(_f(v), 2),
                       "cumCr": round(cum, 2)})
    split = db.execute(
        text("""select left(wbs_element,6) w, count(distinct purchasing_document),
                       sum(net_order_value_inr)/1e7, sum(delivered_value_inr_cr)
                from mt_poamount
                where left(wbs_element,6) = any(:p) and doc_type = 'POrd'
                group by 1 order by 1"""),
        {"p": prefixes},
    ).fetchall()
    return {
        "poCount": totals[0] or 0,
        "orderCr": round(_f(totals[1]), 2),
        "deliveredCr": round(_f(totals[2]), 2),
        "deliveredPct": _pct(_f(totals[2]), _f(totals[1])),
        "receiptSeries": series,
        "byWbs": [{"wbs": r[0],
                   "kind": "supply" if r[0] == cfg["supply_wbs"] else "civil",
                   "poCount": r[1], "orderCr": round(_f(r[2]), 2),
                   "deliveredCr": round(_f(r[3]), 2)} for r in split],
    }
