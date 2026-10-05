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
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any, List, Optional
from collections import defaultdict
from datetime import date, datetime, timedelta
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
        prog = _weightage(db, poid, roots)
        curve = prog
        appr = _approvals(db, poid, roots)
        man = _manpower(db, poid, roots)
        comm = _commercial(db, cfg)
        proc = _procurement(db, poid, cfg)
        contractors = _contractors(db, cfg)
        engineering = _engineering(db, poid, roots)
        construction = _construction(db, poid, roots)
        civil = _civil(db, poid, roots, cfg["containers"])
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
            "civil": civil,
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
        # The pack's own project order (11, 12, 10B, 09, 05B, 08B), which is
        # the register's order - every per-project slide follows it.
        "projects": projects,
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
        text("""select a.wbs_name, a.name, a.status, a.baseline_start_date,
                       a.baseline_finish_date, a.actual_finish_date,
                       a.finish_date, a.activity_id
                from p6_activity a where a.wbs_object_id = any(:w)"""),
        {"w": ids},
    ).fetchall()
    bl = _baseline_of(db, poid)
    items = []
    for r in rows:
        bf = bl(r[7], r[3], r[4])[1]
        items.append({
            "group": r[0], "name": r[1], "status": r[2],
            "baselineFinish": _iso(bf), "actualFinish": _iso(r[5]),
            "forecastFinish": _iso(r[6]),
            "slipDays": (r[5] - bf).days if bf and r[5] else None,
        })
    items.sort(key=_by_baseline("baselineFinish"))

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
                       finish_date, activity_id, baseline_start_date
                from p6_activity
                where project_object_id = :o
                  and (name ilike :comm or name ilike :proj or name ilike :trial)
                order by coalesce(actual_finish_date, finish_date)"""),
        {"o": poid, "comm": "%commissioning phase%",
         "proj": "%project commissioning%", "trial": "%trial run%"},
    ).fetchall()
    bl = _baseline_of(db, poid)
    items = []
    for r in rows:
        bf = bl(r[5], r[6], r[2])[1]
        items.append({
            "name": r[0], "status": r[1], "baselineFinish": _iso(bf),
            "actualFinish": _iso(r[3]), "forecastFinish": _iso(r[4]),
            "slipDays": (r[4] - bf).days if bf and r[4] else None,
        })

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
    electrical_resources = {r for _label, cands, _uom in ELECTRICAL_ELEMENTS for r in cands}
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


# The pack's Civil table, group by group, stage by stage. Each stage names the
# P6 Material resources that make it up; a unit is only through a stage when
# every part of it is, so a multi-resource stage takes the smallest completion.
# P6 counts some stages in sub-units (piles per foundation, m3 of raft) - those
# are scaled to the element's own count so every column reads in the same unit
# as Total Scope, as the pack prints it.
CIVIL_GROUPS = [
    {
        "stages": ["DCIS Piling", "PCC", "Footing & Column Casting",
                   "Slab Casting", "Staircase & Finishing"],
        "elements": [
            ("PCS", "PCS - Column Casting", [
                ["PCS - Driven Cast in-situ Pile"], [],
                ["PCS - Footing & Pile Beam Casting", "PCS - Column Casting"],
                ["PCS - Slab casting"], ["PCS - Stairecase Installation"]]),
            ("SGR", "SGR - Column Casting", [
                ["SGR - Driven Cast in-situ Piling"], ["SGR - PCC"],
                ["SGR - Footing & Pile Beam Casting", "SGR - Column Casting"],
                ["SGR - Slab Casting"], ["SGR - Stairecase Installation"]]),
            ("MCR", "MCR - Column Casting", [
                ["MCR - Driven Cast in-situ Piling"], ["MCR - PCC"],
                ["MCR - Footing & Pile Beam Casting", "MCR - Column Casting"],
                ["MCR - Slab Casting"], ["MCR - Stairecase Installation"]]),
        ],
    },
    {
        "stages": ["Excavation & PCC",
                   "Footing & Wall Casting/ Precast Installation",
                   "Backfilling", "Final Lift & Rail fixing", "Slab work"],
        "elements": [
            ("CT", "CT - Raft Casting of CT", [
                ["CT - Excavation of CT", "CT - PCC of CT"],
                ["CT - Raft Casting of CT", "CT - Dyke Wall of CT"],
                ["CT - Backfilling of CT"],
                ["CT - Final Lift", "CT - Rail Fixing of CT"],
                ["CT - Grade slab of CT"]]),
            ("CSS", "CSS - Footing & Casting", [
                ["CSS - Marking & Excavation", "CSS - PCC"],
                ["CSS - Footing & Casting", "CSS - Wall Casting"],
                ["CSS - Backfilling"], [], ["CSS - Slab Casting"]]),
            ("BOT", "Excavation of BOT", [
                ["Excavation of BOT", "PCC of BOT"],
                ["Erection of Precast Structure BOT"],
                ["Back Filling of BOT"], [], []]),
            ("NIFPS", "Excavation of NIFPS", [
                ["Excavation of NIFPS", "PCC of NIFPS"],
                ["Precast Installation of NIFPS"], [], [], []]),
            # Harmonic Filter work is identified by its WBS (Construction
            # Works > Harmonic Filter), not by resource name - its resources
            # are unprefixed ("PCC") and other WBS reuse the same names.
            ("HF", "HF - PCC", [
                ["HF - Marking & Excavation", "HF - PCC"], [], [], [], ["HF - Raft"]]),
        ],
    },
    {
        "stages": ["DCIS Piling", "Pile Built up", "Precast erection",
                   "Connection with Pile"],
        "elements": [
            ("BCF", "BCF - Precast Erection", [
                ["BCF - Driven Cast in-situ Piling"], ["BCF - Pile Built Up"],
                ["BCF - Precast Erection"],
                ["BCF - Precast Connection with Pile",
                 "BCF - Precast Connection with Pile and Leveling"]]),
        ],
    },
]


def _material_by_resource(db: Session, poid: int, roots: Dict[int, str]):
    """Per Material resource: scope, planned-to-date, actual, and the
    activities carrying it - the shared basis for the Civil and Electrical
    slides, as of P6's own data date."""
    from services.cpag_baseline import baseline_rows

    ids = [k for k, v in roots.items() if v in CONSTRUCTION_BRANCHES]
    data_date = db.execute(
        text("select data_date from p6_project where p6_object_id = :o"),
        {"o": poid}).scalar()
    if not ids:
        return {}, data_date
    as_of = data_date.strftime("%Y-%m") if data_date else "9999-99"
    rows = db.execute(
        text("""select r.resource_name, a.activity_id,
                       coalesce(r.planned_units, 0), coalesce(r.actual_units, 0),
                       a.baseline_start_date, a.baseline_finish_date,
                       (coalesce(w.wbs_name, '') ilike '%harmonic%'
                        or coalesce(pw.wbs_name, '') ilike '%harmonic%')
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                left join p6_wbs_node w on w.p6_object_id = a.wbs_object_id
                left join p6_wbs_node pw on pw.p6_object_id = w.parent_object_id
                where r.project_object_id = :o and r.resource_type = 'Material'
                  and (a.wbs_object_id = any(:w)
                       or coalesce(w.wbs_name, '') ilike '%harmonic%'
                       or coalesce(pw.wbs_name, '') ilike '%harmonic%')"""),
        {"o": poid, "w": ids},
    ).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    live_plan: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    hf_codes = set()
    bl = _baseline_of(db, poid)
    for name, code, planned, actual, bs, bf, is_hf in rows:
        bs, bf = bl(code, bs, bf)
        # Harmonic Filter work reuses generic names ("PCC", "Raft"); tag it by
        # its WBS so it cannot be mistaken for other civil work.
        if is_hf:
            name = f"HF - {name}"
            hf_codes.add(code)
        r = out.setdefault(name, {"scope": 0.0, "planToDate": 0.0,
                                  "actual": 0.0, "activities": set()})
        r["scope"] += float(planned)
        r["actual"] += float(actual)
        r["activities"].add(code)
        _spread_monthly(live_plan[name], bs, bf, float(planned))

    # Plan-to-date from the plan baseline's own quantities and dates, as a
    # share of that baseline's total, applied to today's scope - so a scope
    # change since the re-baseline cannot push plan above scope.
    bl_plan: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for code, name, units, start, finish in baseline_rows(db, poid, "Material"):
        if code in hf_codes:
            name = f"HF - {name}"
        if name in out:
            _spread_monthly(bl_plan[name], start, finish, _f(units))
    for name, r in out.items():
        phased = bl_plan.get(name) or live_plan.get(name) or {}
        total = sum(phased.values())
        done = sum(v for m, v in phased.items() if m <= as_of)
        r["planToDate"] = r["scope"] * (done / total) if total else 0.0
    return out, data_date


def _civil_units(db: Session, poid: int, roots: Dict[int, str]):
    """Per civil work item: scope, planned-to-date and actual in *activities*.

    Since the Sep-26 P6 update civil items ("PCS - Column Casting", "SGR -
    PCC") are Labor resources in man-hours, not Material quantities, so the
    unit is the activity: P6 schedules one per element (PSS-12: 48 PCS
    activities = 48 PCS, 8 SGR = 8 SGR). Actual is completed activities plus
    the done share of those in progress; plan is activities whose plan-baseline
    finish is on or before the data date. Same shape as _material_by_resource,
    so the Civil table reads either."""
    ids = [k for k, v in roots.items() if v in CONSTRUCTION_BRANCHES]
    data_date = db.execute(
        text("select data_date from p6_project where p6_object_id = :o"),
        {"o": poid}).scalar()
    if not ids:
        return {}, data_date
    # Every construction activity with its Labor/Material resource names. An
    # activity is filed under each resource name *and* under its own name:
    # some schedules put the stage only in the activity name, behind a generic
    # resource ("PCS", "LAB - CIVIL") - PSS-08(B) "BLK 1:CIV:CT - CT - PCC of
    # CT", and Harmonic Filter's bare "PCC" / "Raft".
    rows = db.execute(
        text("""select a.activity_id, a.name, a.status,
                       a.baseline_start_date, a.baseline_finish_date,
                       coalesce(a.percent_complete, 0),
                       array_remove(array_agg(distinct r.resource_name), null),
                       sum(r.planned_units), sum(r.actual_units),
                       bool_or(coalesce(w.wbs_name, '') ilike '%harmonic%'
                               or coalesce(pw.wbs_name, '') ilike '%harmonic%')
                from p6_activity a
                left join p6_resource_assignment r
                       on r.activity_object_id = a.p6_object_id
                      and r.resource_type in ('Labor', 'Material')
                left join p6_wbs_node w on w.p6_object_id = a.wbs_object_id
                left join p6_wbs_node pw on pw.p6_object_id = w.parent_object_id
                where a.project_object_id = :o
                  and (a.wbs_object_id = any(:w)
                       or coalesce(w.wbs_name, '') ilike '%harmonic%'
                       or coalesce(pw.wbs_name, '') ilike '%harmonic%')
                group by 1, 2, 3, 4, 5, 6"""),
        {"o": poid, "w": ids},
    ).fetchall()
    bl = _baseline_of(db, poid)
    out: Dict[str, Dict[str, Any]] = {}
    for code, act_name, status, bs, bf, pct, res_names, planned, actual, is_hf in rows:
        # "BLK 1:CIV:CT - CT - PCC of CT" -> "CT - CT - PCC of CT",
        # "CT - PCC of CT", "PCC of CT": every " - " suffix is a candidate.
        tail = (act_name or "").split(":")[-1].strip()
        parts = tail.split(" - ")
        keys = set(res_names or []) | {" - ".join(parts[i:]) for i in range(len(parts))}
        if is_hf:
            keys = {f"HF - {k}" for k in keys}
        if status == "Completed":
            done = 1.0
        elif _f(planned) > 0:
            done = min(1.0, _f(actual) / _f(planned))
        else:
            done = min(1.0, float(pct))
        finish = bl(code, bs, bf)[1]
        due = finish is not None and data_date is not None and finish <= data_date
        for key in keys:
            r = out.setdefault(key, {"scope": 0.0, "planToDate": 0.0,
                                     "actual": 0.0, "activities": set()})
            if code in r["activities"]:
                continue
            r["activities"].add(code)
            r["scope"] += 1
            r["actual"] += done
            r["planToDate"] += 1 if due else 0
    return out, data_date


def _norm_res(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().replace("layling", "laying")
                  .replace("stairecase", "staircase")).strip()


def _find_res(res: Dict[str, Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    """A P6 Material resource by the name one project uses, tolerating the
    spellings other projects use: an element prefix some schedules add
    ("Excavation of NIFPS" vs "NIFPS - Excavation of NIFPS") and the
    "layling" typo. A prefixed name only ever matches its own prefix, so
    "PCS - Column Casting" can never pick up "SGR - Column Casting"."""
    if name in res:
        return res[name]
    target = _norm_res(name)
    for key, val in res.items():
        k = _norm_res(key)
        if k == target or (" - " not in target and k.split(" - ", 1)[-1] == target):
            return val
    return None


def _weightage_progress(db: Session, poid: int, activity_codes, data_date):
    """Plan-to-date and actual % on P6's own weightage for a set of activities
    - the same measure and plan baseline as the S-curve, so an element's
    Progress column cannot disagree with the project curve."""
    from services.cpag_baseline import baseline_rows
    if not activity_codes:
        return None, None
    codes = set(activity_codes)
    as_of = data_date.strftime("%Y-%m") if data_date else "9999-99"
    row = db.execute(
        text("""select sum(r.planned_units), sum(r.actual_units)
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                where r.project_object_id = :o and r.resource_type = 'Nonlabor'
                  and a.activity_id = any(:c)"""),
        {"o": poid, "c": list(codes)},
    ).fetchone()
    planned, actual = (_f(row[0]), _f(row[1])) if row else (0.0, 0.0)
    phased: Dict[str, float] = defaultdict(float)
    for code, _n, units, start, finish in baseline_rows(db, poid, "Nonlabor"):
        if code in codes:
            _spread_monthly(phased, start, finish, _f(units))
    total = sum(phased.values())
    done = sum(v for m, v in phased.items() if m <= as_of)
    plan_pct = min(100.0, round(done / total * 100, 2)) if total else None
    act_pct = _pct(actual, planned)
    return plan_pct, (min(100.0, act_pct) if act_pct is not None else None)


# A stage P6 schedules no activity for, taken from the stage it cannot be done
# without. PCS has no PCC activity on any BESS project (2026-09-30) - PCS goes
# pile -> footing & pile beam - but the pack reports PCS PCC with the footing
# (PSS-11: 54 = 54), and a footing is not cast before its PCC.
INFERRED_STAGES = {"PCC": "Footing & Column Casting"}

# Progress weights per stage, matched to the pack's Progress column
# (2026-09-30): it is not P6's weightage (PCS 85.7% vs the pack's 98%) nor a
# plain count (88.9%). Staircase & Finishing at 4% with the other stages equal
# reproduces PCS 98 / SGR 98 / MCR 97 on PSS-11 exactly; HF 7 of 8 = 88.
STAGE_WEIGHTS = {"Staircase & Finishing": 0.04}


def _infer_stages(stages, plan_row, act_row) -> List[int]:
    """Fill a stage P6 has no activity for from INFERRED_STAGES; returns the
    indexes filled, so the slide can mark them as inferred."""
    filled = []
    for i, st in enumerate(stages):
        src = INFERRED_STAGES.get(st)
        if src in stages and plan_row[i] is None and act_row[i] is None:
            j = stages.index(src)
            if plan_row[j] is not None or act_row[j] is not None:
                plan_row[i], act_row[i] = plan_row[j], act_row[j]
                filled.append(i)
    return filled


def _stage_progress(stages, row, scope) -> Optional[float]:
    """Stage-weighted % complete of one Plan or Actual row: STAGE_WEIGHTS where
    set, the rest shared equally across the stages the element has ("-"
    stages carry no weight)."""
    idx = [i for i, v in enumerate(row) if v is not None]
    if not idx or not scope:
        return None
    fixed = {i: STAGE_WEIGHTS[stages[i]] for i in idx if stages[i] in STAGE_WEIGHTS}
    free = [i for i in idx if i not in fixed]
    share = (1 - sum(fixed.values())) / len(free) if free else 0.0
    w = {**fixed, **{i: share for i in free}}
    total = sum(w.values())
    pct = sum(w[i] * min(1.0, row[i] / scope) for i in idx) / total * 100
    return round(min(100.0, pct), 2)


def _civil(db: Session, poid: int, roots: Dict[int, str],
           containers: Optional[int] = None) -> Dict[str, Any]:
    """The pack's Civil Construction table: per element, a Plan row
    (planned-to-date) and an Actual row, one column per stage, in the element's
    own unit, plus Plan/Actual progress %. Counted in activities
    (_civil_units); BCF is scaled to the container count, as P6 schedules
    several containers' foundations per activity (PSS-12: 48 for 384)."""
    res, data_date = _civil_units(db, poid, roots)
    # Harmonic Filter civil is one activity per stage for every filter; the
    # filter count is its receipt quantity ("HF - Receipt at Site").
    hf_count = int(_f(db.execute(
        text("""select sum(planned_units) from p6_resource_assignment
                where project_object_id = :o and resource_type = 'Material'
                  and resource_name ilike 'HF - Receipt at Site'"""),
        {"o": poid}).scalar()))
    groups = []
    for g in CIVIL_GROUPS:
        elements = []
        for element, scope_res, stage_resources in g["elements"]:
            scope_r = _find_res(res, scope_res)
            if not scope_r or scope_r["scope"] <= 0:
                # The pack's table keeps every element row; one this project's
                # P6 does not carry reads "-" rather than disappearing.
                n = len(stage_resources)
                elements.append({"element": element, "scope": None,
                                 "plan": [None] * n, "actual": [None] * n,
                                 "planPct": None, "actualPct": None})
                continue
            scope = round(scope_r["scope"])
            if element == "BCF" and containers:
                scope = containers
            elif element == "HF" and hf_count:
                scope = hf_count
            plan_row, act_row = [], []
            acts: set = set()
            for names in stage_resources:
                parts = [r for r in (_find_res(res, n) for n in names) if r and r["scope"] > 0]
                if not parts:
                    plan_row.append(None)
                    act_row.append(None)
                    continue
                for p in parts:
                    acts |= p["activities"]
                plan_row.append(round(min(p["planToDate"] / p["scope"] for p in parts) * scope))
                act_row.append(int(min(p["actual"] / p["scope"] for p in parts) * scope))
            inferred = _infer_stages(g["stages"], plan_row, act_row)
            p6_plan_pct, p6_act_pct = _weightage_progress(db, poid, acts, data_date)
            elements.append({
                "element": element, "scope": scope,
                "plan": plan_row, "actual": act_row, "inferred": inferred,
                "planPct": _stage_progress(g["stages"], plan_row, scope),
                "actualPct": _stage_progress(g["stages"], act_row, scope),
                # P6's own activity weightage, kept for audit.
                "p6PlanPct": p6_plan_pct, "p6ActualPct": p6_act_pct,
            })
        groups.append({"stages": g["stages"], "elements": elements})
    return {
        "groups": groups, "dataDate": _iso(data_date),
        "basis": "P6 civil activities as of the P6 data date, one activity = "
                 "one unit (BCF scaled to containers). Plan is activities due "
                 "by the data date on the plan baseline. A stage P6 has no "
                 "activity for is inferred from its prerequisite (PCS PCC = "
                 "Footing & Pile Beam) and listed in `inferred`. Progress is "
                 "stage-weighted (Staircase & Finishing 4%, the other stages "
                 "equal), matched to the pack; P6's own weightage is kept in "
                 "p6PlanPct / p6ActualPct.",
    }


# Pack label -> P6 Material resource, confirmed by matching scope. The pack's
# Electrical table has exactly these ten rows, in this order.
# Where projects book the same work on different resources (PSS-11 carries
# DC/LT cable quantity on "Support erection", PSS-12 and 05(B) on "Cable
# layling"), the candidate with the largest scope is the one in use.
# Resource names differ by project and were renamed in P6 by Sep-26 (PSS-09
# books "HT - Cable", PSS-11 "HT - Cable Laying"), so each row lists every name
# in use; matching is case-insensitive (_find_res).
ELECTRICAL_ELEMENTS = [
    ("HT Cable Laying", ["HT - Cable Laying", "HT - Cable"], "RM"),
    ("FO Cable Laying", ["PPC - FO Cable"], "RM"),
    ("DC Cable Laying", ["DC - Cable laying", "DC - Support erection", "DC - Cable"], "RM"),
    ("LT Cable Laying", ["AC - Cable laying", "AC - Support erection", "LT - Cable",
                         "LT Cable"], "RM"),
    ("Aux Cable Laying", ["AUX - LT Cable Laying", "AUX Cable Laying", "AUX Cable"], "RM"),
    ("Control Cable Laying", ["AUX - Control cable laying",
                              "Control & Communication Cable Laying",
                              "Control & Communication cable"], "RM"),
    ("Battery Container Erection", ["Container Erection", "Battery Container Erection",
                                    "Battery Container"], "NOS"),
    ("PCS Erection", ["PCS Erection", "PCS"], "NOS"),
    ("CT Erection", ["Converter Transformer Erection", "Converter Transformer"], "NOS"),
    ("CSS Erection", ["CSS - CSS Erection", "CSS"], "NOS"),
]


def _electrical(db: Session, poid: int, roots: Dict[int, str]) -> Dict[str, Any]:
    """The pack's Electrical table: UoM, Scope, Plan (quantity whose baseline
    finish has passed), Actual, and each as % of scope - the same basis the
    Civil table uses, as of P6's data date."""
    res, data_date = _material_by_resource(db, poid, roots)
    items = []
    for label, candidates, uom in ELECTRICAL_ELEMENTS:
        found = [r for r in (_find_res(res, c) for c in candidates) if r and r["scope"] > 0]
        r = max(found, key=lambda x: x["scope"]) if found else None
        # Plan % and Actual % are Material quantity over scope - the approved
        # pack's own arithmetic (PSS-11 HT: 34,844 / 54,668 = 64%), not P6
        # weightage (user, 2026-09-28).
        plan_pct = _pct(r["planToDate"], r["scope"]) if r else None
        act_pct = _pct(r["actual"], r["scope"]) if r else None
        # Every row of the pack's table is kept; one P6 does not carry reads "-".
        items.append({
            "element": label, "uom": uom,
            "scope": round(r["scope"]) if r else None,
            "plan": round(r["planToDate"]) if r else None,
            "actual": round(r["actual"]) if r else None,
            "planPct": plan_pct,
            "actualPct": act_pct,
        })
    return {
        "items": items,
        "dataDate": _iso(data_date),
        "basis": "P6 Material resources on Construction activities, as of the "
                 "P6 data date. Plan is quantity due by the data date on the "
                 "plan baseline. Plan % and Actual % are of scope.",
    }


def _manual_entries(db: Session) -> Dict[str, Any]:
    from models import CPAGManualEntry
    from services.cpag_procurement_wbs import procurement_wbs_rows, procurement_wbs_meta

    out = {e.slide_key: {"payload": e.payload, "updatedBy": e.updated_by,
                        "updatedAt": _iso(e.updated_at)}
          for e in db.query(CPAGManualEntry).all()}
    # Procurement's WBS mapping lives in its own tables (mt_zps021,
    # cpag_wbs_baseline), not a JSON blob, so it is assembled fresh here
    # rather than read back from cpag_manual_entry.
    rows = procurement_wbs_rows(db)
    if rows:
        meta = procurement_wbs_meta(db)
        out["procurement_wbs"] = {"payload": {"projects": rows}, "updatedBy": None,
                                  "updatedAt": meta.get("uploadedAt")}
    return out


@router.get("/cpag/manual")
def get_manual_entries(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Team-entered values for the slides no connected system holds."""
    return _manual_entries(db)


@router.put("/cpag/manual/{slide_key}")
def put_manual_entry(slide_key: str, body: Dict[str, Any],
                     db: Session = Depends(get_db)) -> Dict[str, Any]:
    from models import CPAGManualEntry
    if "payload" not in body:
        raise HTTPException(422, "payload is required")
    entry = db.query(CPAGManualEntry).filter(
        CPAGManualEntry.slide_key == slide_key).first()
    if not entry:
        entry = CPAGManualEntry(slide_key=slide_key)
        db.add(entry)
    entry.payload = body["payload"]
    entry.updated_by = body.get("updatedBy")
    entry.updated_at = datetime.utcnow()
    db.commit()
    return {"slideKey": slide_key, "updatedAt": _iso(entry.updated_at)}


@router.post("/cpag/manual/engineering/upload")
async def upload_engineering_mdl(file: UploadFile = File(...),
                                 db: Session = Depends(get_db)) -> Dict[str, Any]:
    """The Engineering Progress page comes from whatever Master Document List
    was last uploaded here - no copy is kept beyond that. Re-upload a newer
    MDL to refresh the page; nothing else changes on this route."""
    from services.cpag_engineering_mdl import parse_engineering_mdl
    from models import CPAGManualEntry

    blob = await file.read()
    try:
        payload = parse_engineering_mdl(blob, file.filename or "upload.xlsx")
    except ValueError as e:
        raise HTTPException(422, str(e))

    entry = db.query(CPAGManualEntry).filter(
        CPAGManualEntry.slide_key == "engineering").first()
    if not entry:
        entry = CPAGManualEntry(slide_key="engineering")
        db.add(entry)
    entry.payload = payload
    entry.updated_by = file.filename
    entry.updated_at = datetime.utcnow()
    db.commit()
    return {"slideKey": "engineering", "projects": sorted(payload["rows"]),
            "asOfLabel": payload.get("asOfLabel"), "updatedAt": _iso(entry.updated_at)}


@router.post("/cpag/manual/procurement/upload")
async def upload_procurement_wbs(file: UploadFile = File(...),
                                 db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Procurement's Packages-through-PO-Date columns come from whatever WBS/
    ZPS021 mapping was last uploaded here (BESS PMAG mail, 2026-09-22/26),
    stored as real rows (mt_zps021, cpag_wbs_baseline) - a fresh upload
    replaces every row, the same convention the ZPSPS007 sync uses. CSS has
    no WBS in this mapping yet and stays on P6, as does every column after
    PO Date."""
    from services.cpag_procurement_wbs import ingest_procurement_wbs

    blob = await file.read()
    try:
        result = ingest_procurement_wbs(db, blob, file.filename or "upload.xlsx")
    except ValueError as e:
        raise HTTPException(422, str(e))
    return result


@router.post("/cpag/baselines/sync")
def sync_baselines(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Re-read each project's plan baseline from P6."""
    from services.cpag_baseline import sync_cpag_baselines
    ids = [r[0] for r in db.execute(
        text("select p6_object_id from p6_project where project_id = any(:p)"),
        {"p": list(BESS_PROJECTS)}).fetchall()]
    return {str(k): v for k, v in sync_cpag_baselines(db, ids).items()}


def _source_stamp(db: Session) -> str:
    """Cheap fingerprint of everything the pack is built from - P6 schedule
    and baselines for the BESS projects, every sync (SAP, Pulse, ...), manual
    entries, the procurement upload and the builder code. Well under a
    second, against ~25s to assemble the payload and ~3 min to render, so an
    unchanged pack opens straight from cache."""
    import hashlib
    from pathlib import Path
    ids = [r[0] for r in db.execute(
        text("select p6_object_id from p6_project where project_id = any(:p)"),
        {"p": list(BESS_PROJECTS)})]
    q = {
        "proj": "select max(data_date), max(last_synced_at) from p6_project where p6_object_id = any(:o)",
        "act": """select count(*), sum(coalesce(percent_complete, 0)), max(actual_finish_date),
                         max(finish_date), count(actual_finish_date)
                  from p6_activity where project_object_id = any(:o)""",
        "res": """select count(*), sum(coalesce(planned_units, 0)), sum(coalesce(actual_units, 0))
                  from p6_resource_assignment where project_object_id = any(:o)""",
        "wbs": "select count(*) from p6_wbs_node where project_object_id = any(:o)",
        "base": "select count(*), max(synced_at) from cpag_baseline_activity",
        "sync": "select max(id) from sync_log where status = 'success'",
        "manual": "select count(*), max(updated_at) from cpag_manual_entry",
        "wbs_up": "select count(*), max(uploaded_at) from cpag_wbs_baseline",
    }
    h = hashlib.sha1()
    for k, sql in q.items():
        h.update(f"{k}={db.execute(text(sql), {'o': ids}).fetchone()}".encode())
    here = Path(__file__).resolve().parent.parent
    for f in ("routers/bess.py", "services/cpag_pptx.py", "services/cpag_render.py",
              "services/cpag_baseline.py", "assets/cpag_reference.pptx"):
        h.update(str((here / f).stat().st_mtime_ns).encode())
    return h.hexdigest()[:16]


@router.get("/portfolio/cpag/preview")
def preview_portfolio(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """The pack as page images of the downloadable deck itself. Served from
    cache while the sources are unchanged (_source_stamp); rebuilt - and
    re-rendered only if the deck content actually changed - otherwise."""
    import json
    from services.cpag_render import render, CACHE, page_path
    stamp = _source_stamp(db)
    stamp_file = CACHE / f"stamp_{stamp}.json"
    if stamp_file.exists():
        out = json.loads(stamp_file.read_text())
        if page_path(out["key"], 1).exists():
            return out
    data = get_portfolio_cpag(db)
    data["manual"] = _manual_entries(db)
    out = render(data, build_portfolio_pptx)
    p6_dates = [(p.get("civil") or {}).get("dataDate") for p in data["projects"]]
    sap = db.execute(text("select max(data_as_on) from sync_log where status = 'success'")).scalar()
    out["asOf"] = {"p6": max((x for x in p6_dates if x), default=None), "sap": _iso(sap)}
    CACHE.mkdir(parents=True, exist_ok=True)
    stamp_file.write_text(json.dumps(out))
    return out


def warm_cpag_preview() -> None:
    """Build the preview ahead of anyone opening it - called after syncs, so
    the ~3 min PowerPoint render happens in the background, not on a click."""
    from database import SessionLocal
    db = SessionLocal()
    try:
        preview_portfolio(db)
    except Exception as e:
        logger.warning(f"CPAG preview warm-up failed: {e}")
    finally:
        db.close()


def _cache_key(key: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{16}", key):
        raise HTTPException(404, "Unknown pack")
    return key


@router.get("/cpag/preview/{key}/{n}.png")
def preview_page(key: str, n: int):
    from fastapi.responses import FileResponse
    from services.cpag_render import page_path
    path = page_path(_cache_key(key), n)
    if not path.exists():
        raise HTTPException(404, "No such page")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


@router.get("/cpag/preview/{key}/deck.pptx")
def preview_deck(key: str):
    """The exact file the preview pages were rendered from."""
    from fastapi.responses import FileResponse
    from services.cpag_render import deck_path
    path = deck_path(_cache_key(key))
    if not path.exists():
        raise HTTPException(404, "Unknown pack")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename="CPAG_BESS_Portfolio.pptx")


@router.get("/portfolio/cpag.pptx")
def download_portfolio_pptx(db: Session = Depends(get_db)) -> Response:
    """The portfolio pack as a PowerPoint file, built from the same payload."""
    data = get_portfolio_cpag(db)
    data["manual"] = _manual_entries(db)
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
    data["manual"] = _manual_entries(db)
    safe = data["meta"]["pss"].replace("(", "").replace(")", "").replace(" ", "_")
    return Response(
        content=build_project_pptx(data),
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="CPAG_{safe}.pptx"'},
    )


@router.post("/eac/reload")
def reload_eac_sap(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Re-read the EAC's SAP extracts (CJI3 -> Incurred, S_ALR_87013558 ->
    Committed) from Data/EAC_BEES."""
    from services.bess_eac import ingest_eac_sap
    try:
        return ingest_eac_sap(db)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))


@router.get("/{project_id}/eac")
def get_eac(project_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """The EAC table for one BESS project (services/bess_eac.py)."""
    from services import bess_eac
    if project_id not in bess_eac.ROOTS:
        raise HTTPException(404, f"{project_id} has no EAC")
    # First read after a deploy: load the SAP extracts if nothing is loaded yet.
    if not db.execute(text("select exists(select 1 from bess_eac_sap_line)")).scalar():
        try:
            bess_eac.ingest_eac_sap(db)
        except FileNotFoundError:
            pass    # the table still renders; Incurred / Committed read 0 with no source listed
    data = bess_eac.build(db, project_id)
    data["pss"] = BESS_PROJECTS[project_id]["pss"]
    return data


# Declared before /eac/{line_key} so "settings" is not read as a row key.
@router.put("/{project_id}/eac/settings")
def put_eac_settings(project_id: str, body: Dict[str, Any],
                     db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Save, per line, the WBS codes the project's EAC leaves out
    ({"excluded": {line_key: [codes]}}). Committed is always POrd + PReq."""
    from services import bess_eac
    try:
        bess_eac.save_settings(db, project_id, body.get("excluded") or {}, body.get("user"))
    except KeyError:
        raise HTTPException(404, f"{project_id} has no EAC")
    except ValueError as e:
        raise HTTPException(422, str(e))
    data = bess_eac.build(db, project_id)
    data["pss"] = BESS_PROJECTS[project_id]["pss"]
    return data


@router.put("/{project_id}/eac/{line_key}")
def put_eac_row(project_id: str, line_key: str, body: Dict[str, Any],
                db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Save a row's editable columns: approved, balance, remarks."""
    from services import bess_eac
    try:
        bess_eac.save_entry(db, project_id, line_key, body)
    except KeyError:
        raise HTTPException(404, f"No EAC row {line_key} for {project_id}")
    except ValueError as e:
        raise HTTPException(422, str(e))
    data = bess_eac.build(db, project_id)
    data["pss"] = BESS_PROJECTS[project_id]["pss"]     # the export names its sheet from it
    return data


@router.get("/{project_id}/cpag")
def get_cpag(project_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ctx = _resolve(db, project_id)
    cfg, poid = ctx["cfg"], ctx["poid"]
    roots = _wbs_roots(db, poid)

    w = _weightage(db, poid, roots)
    curve = {"series": w["series"], "lastActualMonth": w["lastActualMonth"],
             "planBasis": w["planBasis"]}
    comm = _commercial(db, cfg)
    budget = _budget_series(curve["series"], cfg["dispatchable_mwh"])
    return {
        "meta": _meta(ctx),
        "progress": {"buckets": w["buckets"], "totalEarnedPct": w["totalEarnedPct"],
                     "totalPlanPct": w["totalPlanPct"], "basis": w["basis"]},
        "sCurve": curve,
        "procurement": _procurement(db, poid, cfg),
        "approvals": _approvals(db, poid, roots),
        "engineering": _engineering(db, poid, roots),
        "construction": _construction(db, poid, roots),
        "civil": _civil(db, poid, roots, cfg["containers"]),
        "electrical": _electrical(db, poid, roots),
        "commissioning": _commissioning(db, poid),
        "quality": _quality(db, cfg),
        "manpower": _manpower(db, poid, roots),
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


def _weightage(db: Session, poid: int, roots: Dict[int, str]) -> Dict[str, Any]:
    """The Physical Progress slide - its S-curve and its four-milestone table
    - from one set of monthly figures, so the table's FTM row is by
    construction the curve's value for that month.

    Plan: the plan baseline's Nonlabor weightage (B2 or B1 per project,
    cpag_baseline.PLAN_BASELINE), each activity's units spread over its
    planned duration - the method that
    reproduces the pack's PSS-11 plan line to 0.1 point.  Actual: live P6
    actual weightage units spread over each activity's actual start to actual
    finish (or the data date while running).  FTM is the data date's month.
    """
    from services.cpag_baseline import baseline_rows, baseline_name

    data_date = db.execute(
        text("select data_date from p6_project where p6_object_id = :o"),
        {"o": poid}).scalar()
    as_of = data_date.strftime("%Y-%m") if data_date else None

    live = db.execute(
        text("""select a.activity_id, a.wbs_object_id, a.baseline_start_date,
                       a.baseline_finish_date, a.actual_start_date,
                       a.actual_finish_date, sum(r.planned_units),
                       sum(r.actual_units)
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                where r.project_object_id = :o and r.resource_type = 'Nonlabor'
                group by 1, 2, 3, 4, 5, 6"""),
        {"o": poid},
    ).fetchall()
    bl_of = _baseline_of(db, poid)
    live = [(r[0], r[1], *bl_of(r[0], r[2], r[3]), *r[4:]) for r in live]
    bucket_of = {r[0]: BUCKETS.get(roots.get(r[1], ""), "construction") for r in live}

    plan_m: Dict[str, float] = defaultdict(float)
    plan_b: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    bl = baseline_rows(db, poid, "Nonlabor")
    if bl:
        for code, _name, units, start, finish in bl:
            acc: Dict[str, float] = defaultdict(float)
            _spread_monthly(acc, start, finish, _f(units))
            b = bucket_of.get(code, "construction")
            for m, v in acc.items():
                plan_m[m] += v
                plan_b[b][m] += v
        plan_total = sum(_f(r[2]) for r in bl)
        plan_basis = baseline_name(db, poid)
    else:
        for code, _w, bs, bf, _as, _af, planned, _actual in live:
            acc = defaultdict(float)
            _spread_monthly(acc, bs, bf, _f(planned))
            for m, v in acc.items():
                plan_m[m] += v
                plan_b[bucket_of[code]][m] += v
        plan_total = sum(_f(r[6]) for r in live)
        plan_basis = "P6 assigned baseline (B1)"

    act_m: Dict[str, float] = defaultdict(float)
    act_b: Dict[str, float] = defaultdict(float)
    for code, _w, bs, _bf, as_, af, _planned, actual in live:
        if _f(actual):
            _spread_monthly(act_m, as_ or bs, af or data_date, _f(actual))
            act_b[bucket_of[code]] += _f(actual)
    live_total = sum(_f(r[6]) for r in live)

    months = sorted(m for m in set(plan_m) | set(act_m) if m)
    series, cp, ca = [], 0.0, 0.0
    for m in months:
        cp += plan_m[m]
        ca += act_m[m]
        reported = as_of is not None and m <= as_of
        series.append({
            "month": m,
            "planMonthPct": _pct(plan_m[m], plan_total),
            "planCumPct": _pct(cp, plan_total),
            "actualMonthPct": _pct(act_m[m], live_total) if reported else None,
            "actualCumPct": _pct(ca, live_total) if reported else None,
        })

    buckets = []
    for key in BUCKET_ORDER:
        weight = sum(plan_b[key].values())
        to_date = sum(v for m, v in plan_b[key].items() if as_of and m <= as_of)
        plan_pct, earned_pct = _pct(to_date, plan_total), _pct(act_b[key], live_total)
        buckets.append({
            "key": key, "label": BUCKET_LABELS[key],
            "weightPct": _pct(weight, plan_total),
            "planToDatePct": plan_pct, "earnedPct": earned_pct,
            "variancePct": (round(plan_pct - earned_pct, 2)
                            if plan_pct is not None and earned_pct is not None else None),
            "withinBucketPct": _pct(act_b[key], weight),
        })
    total_plan = sum(b["planToDatePct"] or 0 for b in buckets)
    total_act = sum(b["earnedPct"] or 0 for b in buckets)
    return {
        "series": series, "lastActualMonth": as_of, "asOf": as_of,
        "planBasis": plan_basis,
        "buckets": buckets,
        "totalPlanPct": round(total_plan, 2), "totalEarnedPct": round(total_act, 2),
        "basis": f"P6 weightage units. Plan: {plan_basis}, spread over each "
                 f"activity's planned duration. Actual: P6 actual units to the "
                 f"data date.",
    }


def _progress(db: Session, poid: int, roots: Dict[int, str],
              as_of: Optional[str] = None) -> Dict[str, Any]:
    w = _weightage(db, poid, roots)
    return {"buckets": w["buckets"], "totalEarnedPct": w["totalEarnedPct"],
            "totalPlanPct": w["totalPlanPct"], "basis": w["basis"]}


def _s_curve(db: Session, poid: int, roots: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    w = _weightage(db, poid, roots if roots is not None else _wbs_roots(db, poid))
    return {"series": w["series"], "lastActualMonth": w["lastActualMonth"],
            "planBasis": w["planBasis"]}


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
    bl = _baseline_of(db, poid)
    # Delivered at site = P6 Material "Receipt at Site" units. Most packages
    # carry theirs on their own activities; Battery Container and PCS book it
    # on a separate "Receipt at Site" WBS ("BC - Receipt at Site", "PCS
    # Reciept at site" - P6's spelling), so those are taken by name.
    # A package's activities can sit in sub-WBS folders: Battery Container and
    # PCS keep their lots under "<package> > Receipt at Site" and "> MDCC".
    # Reading only the package node itself left their delivery and MDCC dates
    # blank, so each package reads its whole subtree.
    children: Dict[int, List[int]] = defaultdict(list)
    for nid, pid in db.execute(
            text("select p6_object_id, parent_object_id from p6_wbs_node "
                 "where project_object_id = :o"), {"o": poid}):
        children[pid].append(nid)

    def _subtree(root: int) -> List[int]:
        out_ids, stack = [], [root]
        while stack:
            n = stack.pop()
            out_ids.append(n)
            stack.extend(children.get(n, []))
        return out_ids

    receipt_by_wbs = {r[0]: (_f(r[1]), _f(r[2])) for r in db.execute(
        text("""select a.wbs_object_id, sum(r.planned_units), sum(r.actual_units)
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                where r.project_object_id = :o and r.resource_type = 'Material'
                  and r.resource_name ~* 'rec(ei|ie)pt'
                group by 1"""), {"o": poid})}
    receipt_by_kind = {r[0]: (_f(r[1]), _f(r[2])) for r in db.execute(
        text("""select case when resource_name ~* '^bc\\M' then 'battery container'
                            else 'pcs' end,
                       sum(planned_units), sum(actual_units)
                from p6_resource_assignment
                where project_object_id = :o and resource_type = 'Material'
                  and resource_name ~* '^(bc|pcs)\\M.*rec(ei|ie)pt'
                group by 1"""), {"o": poid})}
    for node_id, name in nodes:
        # Every activity attached to this WBS node - not a named subset of
        # milestones - so a tracking step added under a package is picked up
        # without the mapping needing to name it.
        acts = db.execute(
            text("""select name, status, baseline_finish_date,
                           actual_finish_date, finish_date,
                           baseline_start_date, actual_start_date, start_date,
                           activity_id
                    from p6_activity where wbs_object_id = any(:w)"""),
            {"w": _subtree(node_id)},
        ).fetchall()
        acts = [(a[0], a[1], bl(a[8], a[5], a[2])[1], a[3], a[4],
                 bl(a[8], a[5], a[2])[0], a[6], a[7]) for a in acts]
        acts.sort(key=lambda a: (a[5] is None, a[5] or datetime.min))
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
        sub = [receipt_by_wbs[w] for w in _subtree(node_id) if w in receipt_by_wbs]
        receipt = ((sum(p for p, _a in sub), sum(a for _p, a in sub)) if sub else None) or next(
            (v for k, v in receipt_by_kind.items() if base.lower().startswith(k)), None)
        out.append({
            "package": name, "packageBase": base, "scopeQty": qty,
            "sapMaterial": PACKAGE_SAP.get(base),
            # P6 Material receipt units (planned, received); P6 carries no
            # unit of measure, so the pack's own UoM applies downstream.
            "receiptPlanned": receipt[0] if receipt else None,
            "receiptActual": receipt[1] if receipt else None,
            "milestones": [{
                "name": a[0], "status": a[1],
                "baselineStart": _iso(a[5]), "actualStart": _iso(a[6]),
                "forecastStart": _iso(a[7]),
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
                           sum(po_quantities), sum(delivered_qty),
                           min(delivery_date), max(delivery_date)
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
        # CDD (Commercial Delivery Date) is the PO's own delivery date. The
        # ZPSPS007 and ME2J extracts carry no delivery-date column today, so
        # this stays empty until the extract does.
        "cddFirst": _iso(r[8]), "cddLast": _iso(r[9]),
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
                       actual_start_date, actual_finish_date, finish_date,
                       start_date, activity_id
                from p6_activity where wbs_object_id = any(:w)"""),
        {"w": ids},
    ).fetchall()
    bl = _baseline_of(db, poid)
    rows = [(r[0], r[1], *bl(r[8], r[2], r[3]), *r[4:8]) for r in rows]
    rows.sort(key=lambda r: (r[2] is None, r[2] or datetime.min))
    items = [{
        "name": r[0], "status": r[1],
        "baselineStart": _iso(r[2]), "baselineFinish": _iso(r[3]),
        "actualStart": _iso(r[4]), "actualFinish": _iso(r[5]),
        "forecastStart": _iso(r[7]), "forecastFinish": _iso(r[6]),
        "slipDays": (r[5] - r[3]).days if r[3] and r[5] else None,
    } for r in rows]
    return {"items": items, "total": len(items),
            "completed": sum(1 for i in items if i["status"] == "Completed"),
            "inProgress": sum(1 for i in items if i["status"] == "In Progress")}


def _baseline_of(db: Session, poid: int):
    """(activity_code, live baseline start, live baseline finish) -> the
    baseline dates CPAG uses: the project's plan baseline (B2 or B1, per
    services.cpag_baseline.PLAN_BASELINE) once synced, else the live
    schedule's own - the assigned B1."""
    from services.cpag_baseline import baseline_dates
    bl = baseline_dates(db, poid)
    if bl is None:
        return lambda code, start, finish: (start, finish)
    return lambda code, start, finish: bl.get(code, (None, None))


def _by_baseline(key):
    """Sort key: earliest baseline date first, undated last."""
    return lambda it: (it[key] is None, it[key] or "")


def _spread_monthly(acc: Dict[str, float], start, finish, units: float) -> None:
    """Add `units` to `acc` pro rata to the days an activity spends in each
    month - how a labour loading is phased, rather than landing the whole
    activity's units in its finish month."""
    if not units:
        return
    if start is None or finish is None or finish <= start:
        d = finish or start
        if d is not None:
            acc[d.strftime("%Y-%m")] += units
        return
    span = (finish - start).total_seconds()
    cur = start
    while cur < finish:
        nxt = (cur.replace(day=1) + timedelta(days=32)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0)
        end = min(nxt, finish)
        acc[cur.strftime("%Y-%m")] += units * (end - cur).total_seconds() / span
        cur = end


# P6 stores resource assignment Units in hours, not days - the pack's own
# reference figures are mandays. Confirmed live against P6 (2026-09-26): every
# activity on all six BESS projects sits on the same "7 Days x 8 Hours"
# calendar (3,389 of 3,389 checked on PSS-11 alone), so a flat divide is safe
# today; if a project ever carries a different calendar this needs to become
# a per-activity lookup instead of one constant.
HOURS_PER_DAY = 8.0


def _manpower(db: Session, poid: int, roots: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    """Planned and earned mandays per month from P6 Labor units - on the
    construction activities (WBS in CONSTRUCTION_BRANCHES) when `roots` is
    given, the CPAG manpower basis (user, 2026-09-30).

    Plan is each activity's Labor units spread over its baseline dates on the
    project's plan baseline - B2 for PSS-11/12/10(B), B1 for the rest
    (cpag_baseline.PLAN_BASELINE, decided 2026-09-28, the same baseline every
    other CPAG slide uses). Caveat checked 2026-09-26: a re-baseline carries
    already-completed activities' dates at its own data date rather than
    when they were originally planned, so on B2 projects the months before
    the March re-baseline read lumpier against the pack's reference than B1
    did.

    Actual is P6's posted actual labour hours (posted since the Sep-26 update),
    spread over the activity's actual start to its actual finish (or the data
    date while it is still running); planned x percent complete only where
    none is posted. Units are hours in P6; divided by the project's calendar
    (HOURS_PER_DAY) to read as mandays (days basis). Manpower is mandays
    divided by the days in the month - so mandays = manpower x days.
    """
    data_date = db.execute(
        text("select data_date from p6_project where p6_object_id = :o"),
        {"o": poid}).scalar()
    rows = db.execute(
        text("""select a.activity_id, a.baseline_start_date, a.baseline_finish_date,
                       a.actual_start_date, a.actual_finish_date,
                       coalesce(a.percent_complete, 0),
                       sum(r.planned_units), sum(r.actual_units)
                from p6_resource_assignment r
                join p6_activity a on a.p6_object_id = r.activity_object_id
                where r.project_object_id = :o and r.resource_type = 'Labor'
                  -- "LAB - GENERAL" is not site manpower: P6 loads it on office
                  -- and procurement milestones (Release of PR, Placement of
                  -- order, Manufacturing, MDCC, HOTO, Contract Closure) at flat
                  -- 17,080 / 26,368 units - a one-day PR release read as 2,135
                  -- men/day. "LAB - CIVIL" / "LAB - ELECTRICAL" are site work
                  -- (PSS-08(B) books all its piling, casting and laying on
                  -- them) and stay. Site Labor tracks the pack's reported
                  -- headcount (PSS-11 May 207 = 207).
                  and r.resource_name !~* '^lab\\s*-\\s*general'
                  -- Construction activities only (the CPAG manpower basis).
                  and (:all_wbs or a.wbs_object_id = any(:w))
                group by 1, 2, 3, 4, 5, 6"""),
        {"o": poid, "all_wbs": roots is None,
         "w": [k for k, v in (roots or {}).items() if v in CONSTRUCTION_BRANCHES]},
    ).fetchall()
    total = sum(_f(r[6]) for r in rows) / HOURS_PER_DAY
    posted = sum(_f(r[7]) for r in rows) / HOURS_PER_DAY
    plan_m: Dict[str, float] = defaultdict(float)
    earn_m: Dict[str, float] = defaultdict(float)
    bl = _baseline_of(db, poid)
    derived = 0
    for code, bs, bf, as_, af, pct, planned, act_units in rows:
        bs, bf = bl(code, bs, bf)
        planned = _f(planned) / HOURS_PER_DAY
        _spread_monthly(plan_m, bs, bf, planned)
        # P6 posts actual labour hours since the Sep-26 update (PSS-11: 1.42M
        # of 1.98M); use them. Only where nothing is posted fall back to
        # planned x percent complete.
        if _f(act_units) > 0:
            earned = _f(act_units) / HOURS_PER_DAY
        else:
            earned = planned * float(pct)
            derived += 1 if earned else 0
        if earned:
            _spread_monthly(earn_m, as_ or bs, af or data_date, earned)

    # From the first fully covered month on, the site's weekly method replaces
    # the rebuilt figures: the average of the weekly P6 updates, x days.
    # Construction basis only - the snapshots are taken on that labour.
    from services.cpag_manpower import weekly_by_month
    weekly = weekly_by_month(db, poid, HOURS_PER_DAY) if roots is not None else {}

    def _days(m: str) -> int:
        y, mo = int(m[:4]), int(m[5:7])
        return (date(y + (mo == 12), mo % 12 + 1, 1) - date(y, mo, 1)).days

    for m, wk in weekly.items():
        if wk["plan"] is not None:
            plan_m[m] = wk["plan"] * _days(m)
        if wk["actual"] is not None:
            earn_m[m] = wk["actual"] * _days(m)

    as_of = data_date.strftime("%Y-%m") if data_date else None
    months = sorted(m for m in set(plan_m) | set(earn_m) if not as_of or m <= as_of)
    series, cp, ce = [], 0.0, 0.0
    for m in months:
        cp += plan_m[m]
        ce += earn_m[m]
        days = _days(m)
        wk = weekly.get(m) or {}
        series.append({"month": m,
                       "planBasis": "weekly" if wk.get("plan") is not None else "baseline",
                       "actualBasis": "weekly" if wk.get("actual") is not None else "activity",
                       "planMonth": round(plan_m[m]),
                       "planCum": round(cp), "earnedMonth": round(earn_m[m]),
                       "earnedCum": round(ce), "earnedPct": _pct(ce, total),
                       "planManpower": round(plan_m[m] / days),
                       "earnedManpower": round(earn_m[m] / days)})
    return {"series": series, "totalPlannedMandays": round(total),
            "earnedMandays": round(ce), "postedActualUnits": round(posted),
            "asOf": as_of, "derived": derived > 0,
            "basis": "Plan: P6 Labor hours / 8 spread over plan-baseline dates. "
                     "Actual: P6 actual Labor hours / 8 over actual dates "
                     "(planned x % complete only where P6 posted none). "
                     "Manpower = mandays / days in month. From the first month "
                     "fully covered by weekly P6 snapshots: the average of the "
                     "weekly updates (actual = rise in actual hours between "
                     "updates, plan = hours scheduled in the next 7 days) - "
                     "the site's weekly method (services.cpag_manpower)."}


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
