"""What's running, what's down: one status per external feed, derived from
sync_log — the actual outcome of the last sync attempt, not from route
handlers assuming success or from how old the data merely looks.

Status is attempt-based on purpose. We don't know a real sync cadence for
every feed (TC, Capacity and Mapping are run ad hoc, not on a fixed
schedule), so guessing a "stale after N hours" threshold for those would be
invented, not measured. What every feed's sync_log row tells us honestly is
whether the last attempt succeeded, failed, or never ran.
"""
from datetime import datetime, timedelta

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from database import get_db
from services import scheduler

router = APIRouter(prefix="/api/integrations", tags=["Integrations"])

STUCK_AFTER_MINUTES = 60

# key -> (label, sync_log source(s), optional freshness fallback query).
# The freshness fallback is a real "last updated" column on that feed's own
# table — shown only as a secondary "data as of" hint, never used to decide
# running/down. Left blank where no such column exists rather than guessing.
FEEDS = [
    {"key": "sap", "label": "SAP (SharePoint)", "sources": ["sharepoint", "local"],
     "freshness": lambda db: db.query(func.max(models.MTPOAmount.upload_time)).scalar()},
    {"key": "p6", "label": "Primavera P6", "sources": ["p6"],
     "freshness": lambda db: db.query(func.max(models.P6Project.last_synced_at)).scalar()},
    {"key": "tc", "label": "Transmission", "sources": ["tc"], "freshness": None},
    {"key": "pulse", "label": "Pulse (Quality)", "sources": ["pulse"],
     "freshness": lambda db: db.query(func.max(models.PulseNC.last_synced_at)).scalar()},
    {"key": "einvoice", "label": "E-Invoice", "sources": ["einvoice"], "freshness": None},
    {"key": "capacity", "label": "Capacity Milestones", "sources": ["capacity"], "freshness": None},
    {"key": "mapping", "label": "Project Mapping", "sources": ["mapping"], "freshness": None},
]


def _feed_status(db: Session, feed: dict) -> dict:
    SL = models.SyncLog
    rows = db.query(SL).filter(SL.source.in_(feed["sources"])).order_by(SL.started_at.desc()).limit(1).all()
    latest = rows[0] if rows else None
    last_success = (
        db.query(SL)
        .filter(SL.source.in_(feed["sources"]), SL.status == "success")
        .order_by(SL.finished_at.desc())
        .first()
    )

    freshness_fn = feed.get("freshness")
    data_as_of = freshness_fn(db) if freshness_fn else None

    iso = lambda d: d.isoformat() if d else None

    if latest is None:
        # data_as_of may still be non-null (rows exist from before this
        # endpoint shipped, or a one-off manual load) — that is a fact about
        # the data, not a claim that a logged sync ever succeeded, so
        # last_success_at stays null rather than borrowing it.
        return {
            "key": feed["key"], "label": feed["label"], "status": "idle",
            "detail": "No sync has run yet.", "last_attempt_at": None, "last_status": None,
            "last_success_at": None, "data_as_of": iso(data_as_of),
        }

    stuck = latest.status == "running" and (datetime.utcnow() - latest.started_at) > timedelta(minutes=STUCK_AFTER_MINUTES)

    if stuck:
        status, detail = "down", f"Sync started {latest.started_at.isoformat()} and never finished — likely crashed mid-run."
    elif latest.status == "running":
        status, detail = "running", "Sync in progress."
    elif latest.status in ("success", "skipped"):
        status, detail = "running", latest.message or "Last sync succeeded."
    else:  # failed
        status, detail = "down", latest.message or "Last sync failed."

    return {
        "key": feed["key"], "label": feed["label"], "status": status, "detail": detail,
        "last_attempt_at": iso(latest.started_at), "last_status": latest.status,
        "last_success_at": iso(last_success.finished_at) if last_success else None,
        "data_as_of": iso(data_as_of),
    }


# Which sync_schedule row drives each panel feed (the panel's 'sap' is the scheduler's 'sharepoint').
SCHED_SOURCE = {"sap": "sharepoint"}


def _with_schedule(db: Session, feed: dict) -> dict:
    src = SCHED_SOURCE.get(feed["key"], feed["key"])
    sched = db.query(models.SyncSchedule).get(src)
    iso = lambda d: d.isoformat() if d else None
    feed["schedule"] = {
        "source": src,
        "enabled": bool(sched.enabled) if sched else False,
        "interval_minutes": sched.interval_minutes if sched else None,
        "next_run_at": iso(sched.next_run_at) if sched else None,
        "last_run_at": iso(sched.last_run_at) if sched else None,
        "last_duration_s": sched.last_duration_s if sched else None,
        "in_progress": scheduler.is_running(src),
    }
    if feed["schedule"]["in_progress"]:
        feed["status"], feed["detail"] = "running", "Sync in progress."
    elif sched and not sched.enabled and feed["status"] != "down":
        feed["status"] = "paused"
    return feed


@router.get("/status")
def get_integrations_status(db: Session = Depends(get_db)):
    scheduler.ensure_defaults(db)
    feeds = [_with_schedule(db, _feed_status(db, f)) for f in FEEDS]
    nxt = [f["schedule"]["next_run_at"] for f in feeds if f["schedule"]["enabled"] and f["schedule"]["next_run_at"]]
    return {
        "feeds": feeds,
        "summary": {
            "running": sum(1 for f in feeds if f["status"] == "running"),
            "down": sum(1 for f in feeds if f["status"] == "down"),
            "idle": sum(1 for f in feeds if f["status"] == "idle"),
            "paused": sum(1 for f in feeds if f["status"] == "paused"),
            "total": len(feeds),
            "next_run_at": min(nxt) if nxt else None,
            "scheduler_enabled": scheduler._thread is not None,
        },
    }


class ScheduleUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = None


@router.patch("/schedules/{source}")
def update_schedule(source: str, body: ScheduleUpdate, db: Session = Depends(get_db)):
    src = SCHED_SOURCE.get(source, source)
    sched = db.query(models.SyncSchedule).get(src)
    if not sched:
        raise HTTPException(404, f"No schedule for '{source}'")
    if body.interval_minutes is not None:
        if body.interval_minutes < 15 or body.interval_minutes > 10080:
            raise HTTPException(400, "interval_minutes must be between 15 and 10080 (7 days)")
        sched.interval_minutes = body.interval_minutes
        base = sched.last_run_at or datetime.utcnow()
        sched.next_run_at = max(datetime.utcnow(), base + timedelta(minutes=body.interval_minutes))
    if body.enabled is not None:
        sched.enabled = body.enabled
        if body.enabled and not sched.next_run_at:
            sched.next_run_at = datetime.utcnow()
    sched.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True, "source": src, "enabled": sched.enabled, "interval_minutes": sched.interval_minutes,
            "next_run_at": sched.next_run_at.isoformat() if sched.next_run_at else None}


@router.post("/schedules/{source}/run")
def run_schedule_now(source: str):
    """Fire one feed immediately in the background; the panel polls /status to watch it."""
    src = SCHED_SOURCE.get(source, source)
    if src not in scheduler.RUNNERS:
        raise HTTPException(404, f"Unknown feed '{source}'")
    started = scheduler.run_now(src)
    return {"started": started, "source": src, "message": "Started." if started else "Already running."}


@router.get("/health-check")
def check_integrations_now():
    """Live probe, not history: hits every feed right now and returns the
    real error where one fails. On-demand only — never call this on a timer
    or auto-refresh; see services/integration_health.py for why (P6 in
    particular authenticates for real on every call)."""
    from concurrent.futures import ThreadPoolExecutor
    from services import integration_health as h

    checks = {
        "sap": h.check_sap, "p6": h.check_p6, "tc": h.check_tc,
        "pulse": h.check_pulse, "einvoice": h.check_einvoice, "mapping": h.check_mapping,
    }
    with ThreadPoolExecutor(max_workers=len(checks)) as pool:
        futures = {key: pool.submit(fn) for key, fn in checks.items()}
        results = {key: f.result() for key, f in futures.items()}
    results["capacity"] = h.check_capacity(results["p6"])

    now = datetime.utcnow().isoformat()
    labels = {f["key"]: f["label"] for f in FEEDS}
    checked = [
        {"key": key, "label": labels[key], "ok": ok, "detail": detail, "checked_at": now}
        for key, (ok, detail) in results.items()
    ]
    checked.sort(key=lambda c: [f["key"] for f in FEEDS].index(c["key"]))
    return {"checked": checked, "summary": {"ok": sum(1 for c in checked if c["ok"]), "total": len(checked)}}
