"""One sync_log helper every integration's sync route goes through, so the
integrations status panel can report what actually happened on the last run
rather than assuming success because the route returned 200.
"""
from datetime import datetime

import models


def run_logged(db, source: str, fn, status: str = "success"):
    """Runs fn() with no args, recording the attempt to sync_log. Returns
    fn()'s result on success; re-raises on failure after logging it.
    `status` is what a successful fn() is recorded as — 'success' normally,
    'skipped' when the run checked the source and found nothing new."""
    log = models.SyncLog(source=source, status="running")
    db.add(log)
    db.commit()
    try:
        result = fn()
        message = result.get("message") if isinstance(result, dict) else None
        log.status, log.message, log.finished_at = status, message, datetime.utcnow()
        db.commit()
        return result
    except Exception as e:
        db.rollback()
        db.add(log)
        log.status, log.message, log.finished_at = "failed", str(e)[:1000], datetime.utcnow()
        db.commit()
        raise
