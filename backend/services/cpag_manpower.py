"""Weekly manpower for the CPAG pack, from P6 alone.

The site's contractor sheet reports manpower weekly - a Forecast and an
Actual headcount per week - and the pack's monthly figure is the average of
that month's weeks; mandays = that average x days in the month (checked
against the reference pack, 2026-09-30: PSS-11 Aug 289/349/383/384 -> 351).

P6 holds no weekly history to rebuild that from: no period actuals are stored
against its weekly financial periods (0 rows on PSS-11), and every schedule
update overwrites the last look-ahead. So each P6 sync records a snapshot
(models.CPAGManpowerSnapshot) and the weeks are read off consecutive ones:

    Actual   / day = (actual hours now - at the previous update) / 8 / days between
    Forecast / day = hours the current schedule places in [data date, +7 days) / 8 / 7

on the same labour the rest of the manpower slides use: construction WBS,
Labor resources, "LAB - GENERAL" excluded (see routers.bess._manpower).
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

WEEK = timedelta(days=7)


def _labour(db: Session, poid: int):
    from routers.bess import CONSTRUCTION_BRANCHES, _wbs_roots
    roots = _wbs_roots(db, poid)
    return db.execute(
        text(r"""select a.start_date, a.finish_date, a.actual_finish_date,
                        sum(r.planned_units), sum(coalesce(r.actual_units, 0)),
                        sum(coalesce(r.remaining_units, 0))
                 from p6_resource_assignment r
                 join p6_activity a on a.p6_object_id = r.activity_object_id
                 where r.project_object_id = :o and r.resource_type = 'Labor'
                   and r.resource_name !~* '^lab\s*-\s*general'
                   and a.wbs_object_id = any(:w)
                 group by a.p6_object_id, 1, 2, 3"""),
        {"o": poid, "w": [k for k, v in roots.items() if v in CONSTRUCTION_BRANCHES]},
    ).fetchall()


def _overlap_hours(start, finish, hours: float, lo: datetime, hi: datetime) -> float:
    """The share of `hours`, spread evenly over [start, finish), that falls in
    [lo, hi). Remaining work P6 has not dated past the data date counts at lo."""
    if not hours:
        return 0.0
    start = max(start or lo, lo)
    finish = finish or start
    if finish <= start:
        return hours if lo <= start < hi else 0.0
    span = (finish - start).total_seconds()
    inside = (min(finish, hi) - max(start, lo)).total_seconds()
    return hours * max(0.0, inside) / span


def take_snapshot(db: Session, poid: int) -> Optional[Dict[str, Any]]:
    """Record this P6 update of `poid`. Called after every P6 sync."""
    from models import CPAGManpowerSnapshot
    dd = db.execute(text("select data_date from p6_project where p6_object_id = :o"),
                    {"o": poid}).scalar()
    if dd is None:
        return None
    rows = _labour(db, poid)
    actual = sum(float(r[4] or 0) for r in rows)
    planned = sum(float(r[3] or 0) for r in rows)
    forecast = sum(_overlap_hours(st, fi, float(rem or 0), dd, dd + WEEK)
                   for st, fi, af, _p, _a, rem in rows if af is None)
    row = (db.query(CPAGManpowerSnapshot)
           .filter_by(project_object_id=poid, data_date=dd).one_or_none())
    if row is None:
        row = CPAGManpowerSnapshot(project_object_id=poid, data_date=dd)
        db.add(row)
    row.actual_hours, row.forecast_hours_7d, row.planned_hours = actual, forecast, planned
    row.taken_at = datetime.utcnow()
    db.commit()
    return {"dataDate": dd.isoformat(), "actualHours": actual, "forecastHours7d": forecast}


def weekly_by_month(db: Session, poid: int, hours_per_day: float = 8.0) -> Dict[str, Dict[str, Any]]:
    """{"YYYY-MM": {"plan": heads/day, "actual": heads/day, "planWeeks": n,
    "actualWeeks": n}} - the average of the weeks starting in that month.

    A month is returned for a series only once its weeks are covered from the
    start (the first snapshot in its first 7 days, or any later month), so a
    month is never half weekly and half rebuilt from activity dates."""
    snaps = db.execute(
        text("select data_date, actual_hours, forecast_hours_7d "
             "from cpag_manpower_snapshot where project_object_id = :o order by data_date"),
        {"o": poid}).fetchall()
    plan, act = defaultdict(list), defaultdict(list)
    for dd, _a, fc in snaps:
        plan[dd.strftime("%Y-%m")].append(fc / hours_per_day / 7)
    for (d0, a0, _f0), (d1, a1, _f1) in zip(snaps, snaps[1:]):
        days = (d1 - d0).total_seconds() / 86400
        if days >= 1:
            act[d0.strftime("%Y-%m")].append(max(0.0, a1 - a0) / hours_per_day / days)

    def covered(series, first):
        if first is None:
            return {}
        m0 = first.strftime("%Y-%m")
        return {m: v for m, v in series.items() if m > m0 or first.day <= 7}

    plan = covered(plan, snaps[0][0] if snaps else None)
    act = covered(act, snaps[0][0] if len(snaps) > 1 else None)
    out: Dict[str, Dict[str, Any]] = {}
    for m in set(plan) | set(act):
        out[m] = {"plan": sum(plan[m]) / len(plan[m]) if m in plan else None,
                  "actual": sum(act[m]) / len(act[m]) if m in act else None,
                  "planWeeks": len(plan.get(m, [])), "actualWeeks": len(act.get(m, []))}
    return out
