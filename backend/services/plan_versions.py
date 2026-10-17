"""Plan versions: the Ordering Schedule's plan, saved each time it changes.

A change to one project - an LTA, an FTC, a PO landing in SAP - can move other
projects' orders, because they all draw on the same vendor monthly quota. So
that nobody is surprised, the plan is kept as versions:

  - the previous plan is never edited; it is marked superseded (not active) and
    kept, so anyone can see what it was;
  - the revised plan is the active one: reminders, approvals and quotas follow
    it, and other projects take their allocation from it;
  - for each project whose allocation moved, the version records the old and
    the new months, whether its OWN dates changed or it was moved by someone
    else's change, and what that change was.

Versions are written from the standard view (all portfolios, baseline
scenario, ongoing projects, no priority overrides), whoever opens it - a
filtered view competes for quota differently and must not make versions. A row
in any view is annotated from the active version when it shows that version's
revised plan.
"""
import hashlib
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import models
from database import SessionLocal

logger = logging.getLogger(__name__)

RETAIN_DAYS = 14        # a revision is flagged on the schedule this long
KEEP_VERSIONS = 120     # older versions are pruned
TOL = 0.15              # MWp: below this a month has not changed
_lock = threading.Lock()

# What the plan is worked out from, per project, and how it reads in a sentence.
INPUTS = {
    "lta": "LTA", "aop_plan": "AOP", "ftc_date": "FTC date", "module_date": "Module ordering date", "tc_date": "TC date",
    "balance_ordering_mwp": "Balance to order (MWp)", "ordered_mwp": "Ordered (MWp)", "priority": "Priority",
    "type": "Module origin", "cluster": "Portfolio", "is_commissioned": "Commissioned",
}
_DATES = ("lta", "aop_plan", "ftc_date", "module_date", "tc_date")


def is_standard_view(scenario: Optional[str], priorities: Optional[str], portfolio: Optional[str], phase: Optional[str]) -> bool:
    """The view versions are written from."""
    from services import portfolio as portfolio_svc
    return ((scenario or "baseline") == "baseline" and not priorities and not portfolio_svc.is_filtered(portfolio)
            and (phase or "ongoing").strip().lower() in ("ongoing", ""))


def _months(p: dict) -> Dict[str, float]:
    return {mo: round(v, 1) for mo, v in (p.get("month_mwp") or {}).items() if v and v > TOL / 3}


def _row(p: dict) -> dict:
    # The phase records (order / TC / FTC dates, MW) are kept too: they are what the old plan's cells show.
    return {"name": p.get("project_name"), "months": _months(p), "inputs": {k: p.get(k) for k in INPUTS},
            "phases": {mo: rows for mo, rows in (p.get("month_phases") or {}).items() if rows}}


def _same(a: Dict[str, float], b: Dict[str, float]) -> bool:
    return all(abs(a.get(m, 0.0) - b.get(m, 0.0)) <= TOL for m in set(a) | set(b))


def _fingerprint(snap: dict) -> str:
    plan = {pid: r["months"] for pid, r in snap.items()}
    return hashlib.sha1(json.dumps(plan, sort_keys=True).encode()).hexdigest()


def _who(s, pid: str, field: str) -> Optional[str]:
    """Who made an LTA / SCOD edit in Akasha (the date history), if anyone."""
    if field != "lta":
        return None
    try:
        r = (s.query(models.ProjectDateChange)
             .filter(models.ProjectDateChange.mapping_id == int(pid), models.ProjectDateChange.field == "lta")
             .order_by(models.ProjectDateChange.changed_at.desc(), models.ProjectDateChange.id.desc()).first())
    except Exception:  # noqa: BLE001
        return None
    if not r:
        return None
    return r.changed_by if r.source == "manual" and r.changed_by else ("the transmission portal" if r.source == "portal" else None)


def _changes(old: dict, new: dict, s) -> Dict[str, List[dict]]:
    """Input changes per project between two snapshots."""
    out: Dict[str, List[dict]] = {}
    for pid, row in new.items():
        prev = old.get(pid)
        if not prev:
            continue
        for k, label in INPUTS.items():
            a, b = prev["inputs"].get(k), row["inputs"].get(k)
            if a != b and not (k in ("balance_ordering_mwp", "ordered_mwp") and abs((a or 0) - (b or 0)) <= TOL):
                out.setdefault(pid, []).append({"project": row["name"], "field": label, "key": k, "from": a, "to": b,
                                                "by": _who(s, pid, k)})
    return out


def _say(c: dict) -> str:
    by = f" by {c['by']}" if c.get("by") else ""
    return f"{c['field']} of {c['project']}: {c['from'] if c['from'] not in (None, '') else 'not set'} -> {c['to'] if c['to'] not in (None, '') else 'not set'}{by}"


def record(projects: List[dict]) -> Optional[dict]:
    """Save the plan as a new active version if it has changed since the
    active one. Uses its own session, so it never commits a request's work."""
    snap = {str(p["id"]): _row(p) for p in projects}
    fp = _fingerprint(snap)
    first = next(iter(projects[0].get("month_mwp") or {}), None) if projects else None
    with _lock:
        s = SessionLocal()
        try:
            last = (s.query(models.ModulePlanVersion).filter(models.ModulePlanVersion.status == "active")
                    .order_by(models.ModulePlanVersion.version.desc()).first())
            if last is None:
                s.add(models.ModulePlanVersion(version=1, status="active", first_month=first, cause="First saved plan",
                                               snapshot=snap, diff=None, fingerprint=fp))
                s.commit()
                return None
            if last.fingerprint == fp:
                return None
            old = last.snapshot or {}
            rolled = bool(first and last.first_month and first != last.first_month)
            changes = _changes(old, snap, s)
            diff: Dict[str, dict] = {}
            for pid, row in snap.items():
                prev = old.get(pid)
                if not prev or _same(prev["months"], row["months"]):
                    continue
                own = [c for c in changes.get(pid, []) if c["key"] in _DATES + ("balance_ordering_mwp", "ordered_mwp", "priority", "type")]
                because = own or [c for q, cs in changes.items() if q != pid for c in cs
                                  if c["key"] in _DATES + ("balance_ordering_mwp", "ordered_mwp", "priority")][:4]
                if not because and rolled:
                    because = [{"project": row["name"], "field": "A new month began", "key": "month", "from": last.first_month,
                                "to": first, "by": None}]
                # previous_phases: the old plan's own records (dates, MW) for this project, from the version it came from.
                diff[pid] = {"previous": prev["months"], "revised": row["months"], "own": bool(own), "because": because,
                             "previous_phases": prev.get("phases") or {}}
            says = []
            for pid, cs in changes.items():
                says.extend(_say(c) for c in cs if c["key"] in _DATES)
            cause = ("; ".join(says[:3]) + (f" (+{len(says) - 3} more)" if len(says) > 3 else "")) if says else (
                "A new month began" if rolled else "Orders, priorities or capacity changed")
            last.status, last.superseded_at = "superseded", datetime.utcnow()
            s.add(models.ModulePlanVersion(version=last.version + 1, status="active", first_month=first, cause=cause[:600],
                                           snapshot=snap, diff=diff, fingerprint=fp))
            s.commit()
            old_ids = [r.id for r in s.query(models.ModulePlanVersion.id).order_by(models.ModulePlanVersion.version.desc()).offset(KEEP_VERSIONS).all()]
            if old_ids:
                s.query(models.ModulePlanVersion).filter(models.ModulePlanVersion.id.in_(old_ids)).delete(synchronize_session=False)
                s.commit()
            logger.info(f"Plan version {last.version + 1}: {len(diff)} project(s) moved - {cause}")
            return {"version": last.version + 1, "moved": len(diff)}
        except Exception:  # noqa: BLE001 - a version failing to save must never break the schedule
            s.rollback()
            logger.exception("Plan version not saved")
            return None
        finally:
            s.close()


def annotate(projects: List[dict]) -> Optional[dict]:
    """Add `plan_change` to each project the active version moved (while that
    revision is recent and the row shows the revised plan), and return the
    version's summary for the page's notice."""
    s = SessionLocal()
    try:
        v = (s.query(models.ModulePlanVersion).filter(models.ModulePlanVersion.status == "active")
             .order_by(models.ModulePlanVersion.version.desc()).first())
        recent = bool(v and v.diff and v.created_at and v.created_at >= datetime.utcnow() - timedelta(days=RETAIN_DAYS))
        moved = 0
        for p in projects:
            d = (v.diff or {}).get(str(p["id"])) if recent else None
            if d and _same(d["revised"], _months(p)):
                p["plan_change"] = {"version": v.version, "at": v.created_at.isoformat() + "Z", "previous": d["previous"],
                                    "previous_phases": d.get("previous_phases") or {}, "own": d["own"], "because": d["because"]}
                moved += 1
            else:
                p["plan_change"] = None
        if not recent:
            return None
        return {"version": v.version, "at": v.created_at.isoformat() + "Z", "cause": v.cause, "moved": len(v.diff or {}), "shown": moved}
    finally:
        s.close()


def history(limit: int = 30) -> List[dict]:
    """Saved versions, newest first - what changed and who it moved."""
    s = SessionLocal()
    try:
        rows = s.query(models.ModulePlanVersion).order_by(models.ModulePlanVersion.version.desc()).limit(limit).all()
        return [{"version": r.version, "status": r.status, "at": r.created_at.isoformat() + "Z", "cause": r.cause,
                 "superseded_at": r.superseded_at.isoformat() + "Z" if r.superseded_at else None,
                 "moved": [{"project": (r.snapshot or {}).get(pid, {}).get("name"), "own": d["own"], "previous": d["previous"],
                            "revised": d["revised"], "because": d["because"]} for pid, d in (r.diff or {}).items()]}
                for r in rows]
    finally:
        s.close()
