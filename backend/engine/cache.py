"""
Akasha Engine — Freshness Cache (Steps 2-3 of Pipeline)

Per-project metrics cache with sync timestamp tracking.
The key insight: only recompute when upstream data has actually changed.

Cache lifecycle:
1. On first question about a project → compute + cache (SLOW PATH)
2. On subsequent questions → check if P6/SAP/TC sync times have changed
3. If unchanged → return cached data (FAST PATH, ~5ms)
4. If changed → recompute, validate sanity, update cache (SLOW PATH)
"""

import json
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

import models
from engine.tools.p6_tools import p6_get_freshness
from engine.tools.sap_tools import sap_get_freshness
from engine.tools.tc_tools import tc_get_freshness

logger = logging.getLogger(__name__)


# In-memory hot cache for ultra-fast lookups (survives within a single process run)
_hot_cache: dict[str, dict] = {}


def get_current_sync_times(db: Session, project_id: str) -> dict:
    """Get the current sync timestamps from the live database.
    
    This is a cheap lookup (~3ms) — just reading timestamp columns.
    """
    p6_fresh = p6_get_freshness(db, project_id)
    sap_fresh = sap_get_freshness(db, project_id)
    tc_fresh = tc_get_freshness(db)
    
    return {
        "p6_synced_at": p6_fresh.get("synced_at"),
        "sap_synced_at": sap_fresh.get("synced_at"),
        "tc_synced_at": tc_fresh.get("synced_at"),
    }


def check_freshness(db: Session, project_id: str, cache_key: str = "project_360") -> dict:
    """Step 2: Check if cached data for this project is still valid.
    
    Returns:
        {
            "is_stale": bool,
            "cache_exists": bool,
            "current_sync": {...},     # Live DB timestamps
            "cached_sync": {...},      # Timestamps when cache was built
            "cached_at": datetime,     # When the cache was computed
        }
    """
    hot_key = f"{project_id}:{cache_key}"
    
    # Get current sync times from DB (cheap)
    current_sync = get_current_sync_times(db, project_id)
    
    # Check in-memory hot cache first
    if hot_key in _hot_cache:
        hot = _hot_cache[hot_key]
        is_stale = _compare_sync_times(current_sync, hot.get("sync_times", {}))
        return {
            "is_stale": is_stale,
            "cache_exists": True,
            "cache_source": "memory",
            "current_sync": current_sync,
            "cached_sync": hot.get("sync_times", {}),
            "cached_at": hot.get("computed_at"),
        }
    
    # Check DB cache
    cache_entry = db.query(models.MetricsCache).filter(
        models.MetricsCache.project_id == project_id,
        models.MetricsCache.cache_key == cache_key,
    ).first()
    
    if not cache_entry:
        return {
            "is_stale": True,
            "cache_exists": False,
            "cache_source": None,
            "current_sync": current_sync,
            "cached_sync": {},
            "cached_at": None,
        }
    
    cached_sync = {
        "p6_synced_at": cache_entry.p6_synced_at.isoformat() if cache_entry.p6_synced_at else None,
        "sap_synced_at": cache_entry.sap_synced_at.isoformat() if cache_entry.sap_synced_at else None,
        "tc_synced_at": cache_entry.tc_synced_at.isoformat() if cache_entry.tc_synced_at else None,
    }
    
    is_stale = _compare_sync_times(current_sync, cached_sync)
    
    # Populate hot cache if fresh
    if not is_stale:
        _hot_cache[hot_key] = {
            "data": cache_entry.data,
            "sync_times": cached_sync,
            "computed_at": cache_entry.computed_at.isoformat() if cache_entry.computed_at else None,
        }
    
    return {
        "is_stale": is_stale,
        "cache_exists": True,
        "cache_source": "database",
        "current_sync": current_sync,
        "cached_sync": cached_sync,
        "cached_at": cache_entry.computed_at.isoformat() if cache_entry.computed_at else None,
    }


def get_cached_data(db: Session, project_id: str, cache_key: str = "project_360") -> dict | None:
    """Retrieve cached data for a project. Returns None if not cached."""
    hot_key = f"{project_id}:{cache_key}"
    
    # Hot cache first
    if hot_key in _hot_cache:
        logger.debug(f"Cache HIT (memory): {project_id}/{cache_key}")
        return _hot_cache[hot_key].get("data")
    
    # DB cache
    cache_entry = db.query(models.MetricsCache).filter(
        models.MetricsCache.project_id == project_id,
        models.MetricsCache.cache_key == cache_key,
    ).first()
    
    if cache_entry:
        logger.debug(f"Cache HIT (db): {project_id}/{cache_key}")
        # Promote to hot cache
        _hot_cache[hot_key] = {
            "data": cache_entry.data,
            "sync_times": {
                "p6_synced_at": cache_entry.p6_synced_at.isoformat() if cache_entry.p6_synced_at else None,
                "sap_synced_at": cache_entry.sap_synced_at.isoformat() if cache_entry.sap_synced_at else None,
                "tc_synced_at": cache_entry.tc_synced_at.isoformat() if cache_entry.tc_synced_at else None,
            },
            "computed_at": cache_entry.computed_at.isoformat() if cache_entry.computed_at else None,
        }
        return cache_entry.data
    
    logger.debug(f"Cache MISS: {project_id}/{cache_key}")
    return None


def update_cache(db: Session, project_id: str, cache_key: str, data: dict, sync_times: dict):
    """Step 3: Write computed data to both hot cache and DB cache."""
    now = datetime.utcnow()
    hot_key = f"{project_id}:{cache_key}"
    
    # Parse sync times to datetime objects for DB storage
    p6_dt = _parse_iso(sync_times.get("p6_synced_at"))
    sap_dt = _parse_iso(sync_times.get("sap_synced_at"))
    tc_dt = _parse_iso(sync_times.get("tc_synced_at"))
    
    # Upsert into DB
    cache_entry = db.query(models.MetricsCache).filter(
        models.MetricsCache.project_id == project_id,
        models.MetricsCache.cache_key == cache_key,
    ).first()
    
    if cache_entry:
        cache_entry.data = data
        cache_entry.computed_at = now
        cache_entry.p6_synced_at = p6_dt
        cache_entry.sap_synced_at = sap_dt
        cache_entry.tc_synced_at = tc_dt
    else:
        cache_entry = models.MetricsCache(
            project_id=project_id,
            cache_key=cache_key,
            data=data,
            computed_at=now,
            p6_synced_at=p6_dt,
            sap_synced_at=sap_dt,
            tc_synced_at=tc_dt,
        )
        db.add(cache_entry)
    
    db.commit()
    
    # Update hot cache
    _hot_cache[hot_key] = {
        "data": data,
        "sync_times": sync_times,
        "computed_at": now.isoformat(),
    }
    
    logger.info(f"Cache UPDATED: {project_id}/{cache_key}")


def invalidate_cache(db: Session, project_id: str = None):
    """Invalidate cache entries. If project_id is None, invalidate everything."""
    if project_id:
        db.query(models.MetricsCache).filter(
            models.MetricsCache.project_id == project_id
        ).delete()
        # Clear hot cache for this project
        keys_to_remove = [k for k in _hot_cache if k.startswith(f"{project_id}:")]
        for k in keys_to_remove:
            del _hot_cache[k]
        logger.info(f"Cache INVALIDATED: {project_id}")
    else:
        db.query(models.MetricsCache).delete()
        _hot_cache.clear()
        logger.info("Cache INVALIDATED: ALL")
    db.commit()


def validate_sanity(old_data: dict, new_data: dict) -> list[str]:
    """Sanity check: flag wild swings between old and new data.
    
    Returns list of warning messages if anomalies detected.
    """
    warnings = []
    
    if not old_data or not new_data:
        return warnings
    
    # Check SPI swing
    old_spi = _extract_nested(old_data, "spi")
    new_spi = _extract_nested(new_data, "spi")
    if old_spi and new_spi:
        delta = abs(new_spi - old_spi)
        if delta > 0.3:
            warnings.append(
                f"SPI changed significantly: {old_spi:.2f} → {new_spi:.2f} "
                f"(Δ{delta:.2f}). Verify data quality."
            )
    
    # Check activity count swing
    old_count = _extract_nested(old_data, "activity_count")
    new_count = _extract_nested(new_data, "activity_count")
    if old_count and new_count and old_count > 0:
        pct_change = abs(new_count - old_count) / old_count
        if pct_change > 0.5:
            warnings.append(
                f"Activity count changed by {pct_change*100:.0f}%: "
                f"{old_count} → {new_count}. Possible data sync issue."
            )
    
    return warnings


# ── Helpers ──

def _compare_sync_times(current: dict, cached: dict) -> bool:
    """Returns True if data is stale (sync times differ)."""
    for key in ("p6_synced_at", "sap_synced_at", "tc_synced_at"):
        current_val = current.get(key)
        cached_val = cached.get(key)
        if current_val and cached_val and current_val != cached_val:
            return True
    return False


def _parse_iso(val) -> datetime | None:
    """Parse an ISO datetime string to datetime object."""
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def _extract_nested(data: dict, key: str):
    """Extract a value from possibly nested dict (tries top-level, then p6 sub-dict)."""
    if key in data:
        return data[key]
    if "p6" in data and isinstance(data["p6"], dict) and key in data["p6"]:
        return data["p6"][key]
    return None
