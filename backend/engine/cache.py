"""
Akasha Engine — Freshness Cache (Steps 2-3 of Pipeline)

Per-project metrics cache with sync timestamp tracking.
The key insight: only recompute when upstream data has actually changed.

Cache lifecycle:
1. On first question about a project → compute + cache (SLOW PATH)
2. On subsequent questions → check if P6/SAP/TC/Pulse sync times have changed
3. If unchanged → return cached data (FAST PATH, ~5ms)
4. If changed → recompute, validate sanity, update cache (SLOW PATH)
"""

import json
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)


# In-memory hot cache for ultra-fast lookups (survives within a single process run)
_hot_cache: dict[str, dict] = {}
_SYNC_KEYS = (
    "p6_synced_at",
    "sap_synced_at",
    "tc_synced_at",
    "pulse_synced_at",
    "p6_sync_version",
    "sap_sync_version",
    "tc_sync_version",
    "pulse_sync_version",
    "mapping_sync_version",
    "capacity_sync_version",
)
_CACHE_ENVELOPE_KEY = "__akasha_metrics_cache_v1__"


def get_current_sync_times(db: Session, project_id: str) -> dict:
    """Get the current sync timestamps from the live database.
    
    This is a cheap lookup (~3ms) — just reading timestamp columns.
    """
    from engine.tools.p6_tools import p6_get_freshness
    from engine.tools.sap_tools import sap_get_freshness
    from engine.tools.tc_tools import tc_get_freshness

    p6_fresh = p6_get_freshness(db, project_id)
    sap_fresh = sap_get_freshness(db, project_id)
    tc_fresh = tc_get_freshness(db)
    pulse_synced_at = db.query(
        func.max(models.PulseNC.last_synced_at)
    ).scalar()
    pulse_rfi_synced_at = db.query(
        func.max(models.PulseRFI.last_synced_at)
    ).scalar()
    pulse_latest = max(
        (value for value in (pulse_synced_at, pulse_rfi_synced_at) if value is not None),
        default=None,
    )
    
    from services.freshness_service import get_sync_versions

    versions = get_sync_versions(db)
    return {
        "p6_synced_at": p6_fresh.get("synced_at"),
        "sap_synced_at": sap_fresh.get("synced_at"),
        "tc_synced_at": tc_fresh.get("synced_at"),
        "pulse_synced_at": pulse_latest.isoformat() if pulse_latest else None,
        "p6_sync_version": versions.get("P6"),
        "sap_sync_version": versions.get("SAP"),
        "tc_sync_version": versions.get("TC"),
        "pulse_sync_version": versions.get("Pulse"),
        "mapping_sync_version": versions.get("Mapping"),
        "capacity_sync_version": versions.get("Capacity"),
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
    
    cached_data, cached_extra_sync = _unpack_cache_data(cache_entry.data)
    cached_sync = {
        "p6_synced_at": cache_entry.p6_synced_at.isoformat() if cache_entry.p6_synced_at else None,
        "sap_synced_at": cache_entry.sap_synced_at.isoformat() if cache_entry.sap_synced_at else None,
        "tc_synced_at": cache_entry.tc_synced_at.isoformat() if cache_entry.tc_synced_at else None,
        "pulse_synced_at": cached_extra_sync.get("pulse_synced_at"),
        **{key: cached_extra_sync.get(key) for key in _SYNC_KEYS if key.endswith("_version")},
    }
    
    is_stale = _compare_sync_times(current_sync, cached_sync)
    
    # Populate hot cache if fresh
    if not is_stale:
        _hot_cache[hot_key] = {
            "data": cached_data,
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
    if check_freshness(db, project_id, cache_key)["is_stale"]:
        return None
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
        cached_data, cached_extra_sync = _unpack_cache_data(cache_entry.data)
        # Promote to hot cache
        _hot_cache[hot_key] = {
            "data": cached_data,
            "sync_times": {
                "p6_synced_at": cache_entry.p6_synced_at.isoformat() if cache_entry.p6_synced_at else None,
                "sap_synced_at": cache_entry.sap_synced_at.isoformat() if cache_entry.sap_synced_at else None,
                "tc_synced_at": cache_entry.tc_synced_at.isoformat() if cache_entry.tc_synced_at else None,
                "pulse_synced_at": cached_extra_sync.get("pulse_synced_at"),
                **{key: cached_extra_sync.get(key) for key in _SYNC_KEYS if key.endswith("_version")},
            },
            "computed_at": cache_entry.computed_at.isoformat() if cache_entry.computed_at else None,
        }
        return cached_data
    
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
    stored_data = _pack_cache_data(data, sync_times)
    
    # Upsert into DB
    cache_entry = db.query(models.MetricsCache).filter(
        models.MetricsCache.project_id == project_id,
        models.MetricsCache.cache_key == cache_key,
    ).first()
    
    if cache_entry:
        cache_entry.data = stored_data
        cache_entry.computed_at = now
        cache_entry.p6_synced_at = p6_dt
        cache_entry.sap_synced_at = sap_dt
        cache_entry.tc_synced_at = tc_dt
    else:
        cache_entry = models.MetricsCache(
            project_id=project_id,
            cache_key=cache_key,
            data=stored_data,
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
    for key in _SYNC_KEYS:
        current_val = _normalize_sync_time(current.get(key))
        cached_val = _normalize_sync_time(cached.get(key))
        if current_val != cached_val:
            return True
    return False


def _normalize_sync_time(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        return value


def _pack_cache_data(data: dict, sync_times: dict) -> dict:
    """Persist sync metadata not represented by the legacy cache columns."""
    return {
        _CACHE_ENVELOPE_KEY: True,
        "data": data,
        "sync_times": {
            key: sync_times.get(key)
            for key in _SYNC_KEYS
            if key == "pulse_synced_at" or key.endswith("_version")
        },
    }


def _unpack_cache_data(stored_data: dict) -> tuple[dict, dict]:
    """Read both legacy plain payloads and metadata-enveloped payloads."""
    if isinstance(stored_data, dict) and stored_data.get(_CACHE_ENVELOPE_KEY) is True:
        return stored_data.get("data", {}), stored_data.get("sync_times", {})
    return stored_data, {}


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
