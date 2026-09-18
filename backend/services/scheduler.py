"""In-process sync scheduler — every feed runs itself on its own interval.

No external dependency: a daemon thread wakes every 30 s, and for each enabled
feed whose next_run_at has passed, runs that feed's sync in a worker thread.
Each run goes through sync_log (via run_logged / sap_sync), so the Integrations
panel reads scheduled and manual runs from the same place.

SharePoint is the one feed that checks for NEW data before doing work: it
lists the folder and only ingests when an extract is newer than the last
successful data_as_on. A tick with nothing new is logged as 'skipped' so the
panel can show "checked at 10:05, no new files" rather than looking dead.

Overlap is prevented per feed with a lock, so a slow 12-minute SAP ingest can
never be started twice.
"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict

import models
from database import SessionLocal

logger = logging.getLogger(__name__)

TICK_SECONDS = 30

# source -> (label, default interval minutes). Intervals are editable from the
# panel; these are only what a fresh database starts with.
DEFAULTS: Dict[str, tuple] = {
    "sharepoint": ("SAP (SharePoint)", 60),        # checks hourly, ingests only when a newer extract exists
    "p6":         ("Primavera P6", 360),
    "pulse":      ("Pulse (Quality)", 120),
    "einvoice":   ("E-Invoice", 240),
    "tc":         ("Transmission", 720),
    "capacity":   ("Capacity Milestones", 1440),
    "mapping":    ("Project Mapping", 1440),
}

_locks: Dict[str, threading.Lock] = {k: threading.Lock() for k in DEFAULTS}
_running: Dict[str, datetime] = {}
_thread: threading.Thread | None = None


def is_running(source: str) -> bool:
    return source in _running


# ── the actual work per feed ─────────────────────────────────────────────────

def _run_sharepoint(db):
    """Only ingest when SharePoint holds something newer than what is loaded."""
    from services.sharepoint_service import SharePointService
    from services.sap_sync import sync_sap_from_sharepoint
    from scripts.ingest_sap_data import SAP_FILE_PATTERNS
    from services.sync_log_util import run_logged

    sp = SharePointService()
    files = [f for f in sp.list_files_in_target_folder()
             if any(p.match(f["name"]) for p in SAP_FILE_PATTERNS.values()) and f.get("modified")]
    newest = max((datetime.fromisoformat(f["modified"].replace("Z", "+00:00")).replace(tzinfo=None) for f in files), default=None)
    SL = models.SyncLog
    last = db.query(SL).filter(SL.source.in_(["sharepoint", "local"]), SL.status == "success").order_by(SL.finished_at.desc()).first()
    if newest and last and last.data_as_on and newest <= last.data_as_on:
        run_logged(db, "sharepoint", lambda: {"message": f"Checked SharePoint — no extract newer than {last.data_as_on:%d-%m-%y %H:%M}."}, status="skipped")
        return
    sync_sap_from_sharepoint(db)


def _run_p6(db):
    from services.p6_service import P6Service
    from services.sync_log_util import run_logged
    def _do():
        r = P6Service().full_sync(db)
        return {"message": f"Synced {r['projects_synced']} projects and {r['baselines_synced']} baselines", **r}
    run_logged(db, "p6", _do)


def _run_pulse(db):
    from services.pulse_service import PulseService
    from services.sync_log_util import run_logged
    def _do():
        r = PulseService().full_sync(db)
        return {"message": f"Synced {r['ncs']} NCs and {r['rfis']} RFIs from Pulse", **r}
    run_logged(db, "pulse", _do)


def _run_einvoice(db):
    from scripts.sync_einvoice_live import sync_einvoice_live
    from services.sync_log_util import run_logged
    run_logged(db, "einvoice", lambda: (sync_einvoice_live(), {"message": "Synced E-Invoice data"})[1])


def _run_capacity(db):
    from scripts.sync_capacity_milestones import fetch_capacity_milestones
    from services.sync_log_util import run_logged
    run_logged(db, "capacity", lambda: (fetch_capacity_milestones(), {"message": "Synced capacity milestones"})[1])


def _run_mapping(db):
    from scripts.ingest_mapping import ingest_mapping
    from services.sync_log_util import run_logged
    run_logged(db, "mapping", lambda: (ingest_mapping(), {"message": "Synced project mapping"})[1])


def _run_tc(db):
    from services.tc_sync import run_sync
    run_sync()  # logs its own outcome to sync_log


RUNNERS: Dict[str, Callable] = {
    "sharepoint": _run_sharepoint, "p6": _run_p6, "pulse": _run_pulse, "einvoice": _run_einvoice,
    "capacity": _run_capacity, "mapping": _run_mapping, "tc": _run_tc,
}


# ── schedule persistence ─────────────────────────────────────────────────────

def ensure_defaults(db):
    """Seed sync_schedule for any feed missing a row. Idempotent."""
    existing = {r.source for r in db.query(models.SyncSchedule).all()}
    now = datetime.utcnow()
    for src, (_, minutes) in DEFAULTS.items():
        if src not in existing:
            # Stagger first runs so a fresh start doesn't fire everything at once.
            db.add(models.SyncSchedule(source=src, enabled=True, interval_minutes=minutes,
                                       next_run_at=now + timedelta(minutes=2 + 3 * len(existing)), updated_at=now))
            existing.add(src)
    db.commit()


def run_now(source: str) -> bool:
    """Fire a feed immediately in a worker thread. False if already running."""
    if source not in RUNNERS or is_running(source):
        return False
    threading.Thread(target=_execute, args=(source,), daemon=True, name=f"sync-{source}").start()
    return True


def _execute(source: str):
    lock = _locks[source]
    if not lock.acquire(blocking=False):
        return
    _running[source] = datetime.utcnow()
    started = time.time()
    db = SessionLocal()
    try:
        try:
            RUNNERS[source](db)
        except Exception as e:  # already recorded in sync_log by run_logged / sap_sync
            logger.error(f"[scheduler] {source} failed: {e}")
        sched = db.query(models.SyncSchedule).get(source)
        if sched:
            now = datetime.utcnow()
            sched.last_run_at = now
            sched.last_duration_s = round(time.time() - started, 1)
            sched.next_run_at = now + timedelta(minutes=sched.interval_minutes)
            db.commit()
    finally:
        db.close()
        _running.pop(source, None)
        lock.release()


def _tick():
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        due = db.query(models.SyncSchedule).filter(
            models.SyncSchedule.enabled.is_(True), models.SyncSchedule.next_run_at <= now).all()
        for s in due:
            if s.source in RUNNERS and not is_running(s.source):
                run_now(s.source)
    except Exception as e:
        logger.error(f"[scheduler] tick failed: {e}")
    finally:
        db.close()


def _loop():
    logger.info("[scheduler] started")
    while True:
        _tick()
        time.sleep(TICK_SECONDS)


def start():
    """Idempotent. Set AKASHA_SCHEDULER=0 to run the API without it."""
    global _thread
    if _thread or os.getenv("AKASHA_SCHEDULER", "1") in ("0", "false", "no"):
        return
    db = SessionLocal()
    try:
        models.SyncSchedule.__table__.create(bind=db.get_bind(), checkfirst=True)
        ensure_defaults(db)
    finally:
        db.close()
    _thread = threading.Thread(target=_loop, daemon=True, name="akasha-scheduler")
    _thread.start()
