"""
P6 baselines behind the CPAG pack.

Every CPAG slide that shows a "baseline" date, or phases plan quantity over
baseline dates, reads the baseline named per project in PLAN_BASELINE
(decided 2026-09-28): the March re-baseline B2 for PSS-11, PSS-12 and
PSS-10(B); the November original B1 for PSS-09, PSS-05(B) and PSS-08(B),
which have no B2.

The live schedule's baseline_* dates are the project's *assigned* P6 baseline
- B1 on all six projects (checked 2026-09-28). A baseline activity's
PlannedStartDate/PlannedFinishDate is exactly what P6 reports as the live
activity's BaselineStartDate/FinishDate (3,445 of 3,445 on PSS-09 B1, 3,335 of
3,335 on PSS-11 B1), so reading the chosen baseline's planned dates is the
same field on a different baseline.  An activity added after the baseline was
taken has no baseline date in P6 (75 of 75 such on PSS-11) and gets none here.

Baseline projects are separate P6 projects, so their activities and resource
assignments are read from P6 and stored here, keyed back to the live
project by activity code.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Live P6 project id -> the baseline tag its CPAG slides plan against.
PLAN_BASELINE: Dict[str, str] = {
    "AGE27BL_PSS11_FINAL": "B2",
    "AGE27CL_PSS12_FINAL": "B2",
    "ARE35L_PSS10B_FINAL": "B2",
    "AGE27AL_PSS09_FINAL": "B1",
    "AGE44L_PSS5B_FINAL": "B1",
    "AGE35L_PSS8B_FINAL": "B1",
}


def _p6_get(p6, endpoint: str, fields: str, flt: str) -> List[Dict[str, Any]]:
    resp = requests.get(f"{p6.base_url}/{endpoint}", headers=p6.headers,
                        params={"Fields": fields, "Filter": flt}, timeout=300,
                        verify=False, proxies=p6.proxies)
    resp.raise_for_status()
    return resp.json()


def _parse(ts: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(ts[:19]) if ts else None


def choose_baseline(baselines: List[Dict[str, Any]], tag: str) -> Optional[Dict[str, Any]]:
    """The baseline named "... - <tag>". No fallback to another tag: a
    project planned on B2 must not silently read B1."""
    for b in baselines:
        if (b.get("Name") or "").strip().endswith(f"- {tag}"):
            return b
    return None


def sync_cpag_baselines(db: Session, project_object_ids: List[int], p6=None) -> Dict[str, Any]:
    from models import CPAGBaselineActivity, CPAGBaselineAssignment
    if p6 is None:
        from services.p6_service import P6Service
        p6 = P6Service()

    tag_of = {r[0]: PLAN_BASELINE.get(r[1]) for r in db.execute(
        text("select p6_object_id, project_id from p6_project "
             "where p6_object_id = any(:o)"), {"o": list(project_object_ids)})}

    summary: Dict[str, Any] = {}
    for poid in project_object_ids:
        tag = tag_of.get(poid)
        if not tag:
            summary[poid] = "no plan baseline configured"
            continue
        baselines = _p6_get(p6, "baselineProject", "ObjectId,Name,DataDate",
                            f"OriginalProjectObjectId={poid}")
        chosen = choose_baseline(baselines, tag)
        if not chosen:
            # Keep whatever was stored before rather than wiping the plan.
            summary[poid] = f"no '- {tag}' baseline in P6"
            logger.error("CPAG baseline %s not found in P6 for project %s", tag, poid)
            continue
        bl_id = int(chosen["ObjectId"])
        acts = _p6_get(p6, "activity",
                       "ObjectId,Id,PlannedStartDate,PlannedFinishDate",
                       f"ProjectObjectId={bl_id}")
        by_obj = {a["ObjectId"]: a for a in acts}
        ras = _p6_get(p6, "resourceAssignment",
                      "ActivityObjectId,ResourceType,ResourceName,PlannedUnits",
                      f"ProjectObjectId={bl_id}")

        for model in (CPAGBaselineActivity, CPAGBaselineAssignment):
            db.query(model).filter(model.project_object_id == poid).delete()
        now = datetime.utcnow()
        name = chosen.get("Name")
        act_rows = [CPAGBaselineActivity(
            project_object_id=poid, baseline_object_id=bl_id, baseline_name=name,
            activity_code=a.get("Id"),
            planned_start=_parse(a.get("PlannedStartDate")),
            planned_finish=_parse(a.get("PlannedFinishDate")),
            synced_at=now,
        ) for a in acts]
        rows = []
        for r in ras:
            a = by_obj.get(r.get("ActivityObjectId"))
            if not a:
                continue
            rows.append(CPAGBaselineAssignment(
                project_object_id=poid, baseline_object_id=bl_id,
                baseline_name=name, activity_code=a.get("Id"),
                resource_type=r.get("ResourceType"),
                resource_name=r.get("ResourceName"),
                planned_units=float(r.get("PlannedUnits") or 0),
                planned_start=_parse(a.get("PlannedStartDate")),
                planned_finish=_parse(a.get("PlannedFinishDate")),
                synced_at=now,
            ))
        db.add_all(act_rows)
        db.add_all(rows)
        db.commit()
        summary[poid] = {"baseline": name, "activities": len(act_rows),
                         "assignments": len(rows)}
        logger.info("CPAG baseline %s for project %s: %d activities, %d assignments",
                    name, poid, len(act_rows), len(rows))
    return summary


def baseline_rows(db: Session, poid: int, resource_type: str):
    """(activity_code, resource_name, planned_units, start, finish) for one
    project's plan baseline and resource type."""
    return db.execute(
        text("""select activity_code, resource_name, planned_units,
                       planned_start, planned_finish
                from cpag_baseline_assignment
                where project_object_id = :o and resource_type = :t"""),
        {"o": poid, "t": resource_type},
    ).fetchall()


def baseline_dates(db: Session, poid: int) -> Optional[Dict[str, Tuple[Any, Any]]]:
    """activity_code -> (baseline start, baseline finish) on the project's plan
    baseline, or None when it has not been synced - the caller then keeps
    the live schedule's baseline_* dates (the assigned B1)."""
    rows = db.execute(
        text("""select activity_code, planned_start, planned_finish
                from cpag_baseline_activity where project_object_id = :o"""),
        {"o": poid},
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows} if rows else None


def baseline_name(db: Session, poid: int) -> Optional[str]:
    return db.execute(
        text("select max(baseline_name) from cpag_baseline_activity "
             "where project_object_id = :o"), {"o": poid}).scalar()
