"""
P6 re-baselines behind the CPAG pack's plan line.

The live schedule's baseline_* dates are the project's original (November)
baseline. The pack plans against the March re-baseline - "B2" - where a
project has one: spreading B2's weightage units over each activity's planned
duration reproduces the pack's PSS-11 plan line to within 0.1 point every
month (checked 2026-09-25). PSS-09, 05(B) and 08(B) have only B1.

Baseline projects are separate P6 projects, so their activities and resource
assignments are read from P6 and stored here, keyed back to the live
project by activity code.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _p6_get(p6, endpoint: str, fields: str, flt: str) -> List[Dict[str, Any]]:
    resp = requests.get(f"{p6.base_url}/{endpoint}", headers=p6.headers,
                        params={"Fields": fields, "Filter": flt}, timeout=300,
                        verify=False, proxies=p6.proxies)
    resp.raise_for_status()
    return resp.json()


def _parse(ts: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(ts[:19]) if ts else None


def choose_baseline(baselines: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The re-baseline the pack plans against: "- B2", else "- B1"."""
    for tag in ("- B2", "- B1"):
        for b in baselines:
            if (b.get("Name") or "").strip().endswith(tag):
                return b
    return None


def sync_cpag_baselines(db: Session, project_object_ids: List[int], p6=None) -> Dict[str, Any]:
    from models import CPAGBaselineAssignment
    if p6 is None:
        from services.p6_service import P6Service
        p6 = P6Service()

    summary: Dict[str, Any] = {}
    for poid in project_object_ids:
        baselines = _p6_get(p6, "baselineProject", "ObjectId,Name,DataDate",
                            f"OriginalProjectObjectId={poid}")
        chosen = choose_baseline(baselines)
        if not chosen:
            summary[poid] = "no B1/B2 baseline"
            continue
        bl_id = int(chosen["ObjectId"])
        acts = _p6_get(p6, "activity",
                       "ObjectId,Id,PlannedStartDate,PlannedFinishDate",
                       f"ProjectObjectId={bl_id}")
        by_obj = {a["ObjectId"]: a for a in acts}
        ras = _p6_get(p6, "resourceAssignment",
                      "ActivityObjectId,ResourceType,ResourceName,PlannedUnits",
                      f"ProjectObjectId={bl_id}")

        db.query(CPAGBaselineAssignment).filter(
            CPAGBaselineAssignment.project_object_id == poid).delete()
        now = datetime.utcnow()
        rows = []
        for r in ras:
            a = by_obj.get(r.get("ActivityObjectId"))
            if not a:
                continue
            rows.append(CPAGBaselineAssignment(
                project_object_id=poid, baseline_object_id=bl_id,
                baseline_name=chosen.get("Name"), activity_code=a.get("Id"),
                resource_type=r.get("ResourceType"),
                resource_name=r.get("ResourceName"),
                planned_units=float(r.get("PlannedUnits") or 0),
                planned_start=_parse(a.get("PlannedStartDate")),
                planned_finish=_parse(a.get("PlannedFinishDate")),
                synced_at=now,
            ))
        db.add_all(rows)
        db.commit()
        summary[poid] = {"baseline": chosen.get("Name"), "assignments": len(rows)}
        logger.info("CPAG baseline %s for project %s: %d assignments",
                    chosen.get("Name"), poid, len(rows))
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


def baseline_name(db: Session, poid: int) -> Optional[str]:
    return db.execute(
        text("select max(baseline_name) from cpag_baseline_assignment "
             "where project_object_id = :o"), {"o": poid}).scalar()
