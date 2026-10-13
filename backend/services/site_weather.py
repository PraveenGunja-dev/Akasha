"""Site weather for Advanced AI planning: how fast a site can work on a given
day, 1.0 = an average day at that site.

Two sources, nearest first:
  * the next ~16 days: Open-Meteo's live daily forecast at the site
    (the same provider as engine/intelligence/weather_intel.py);
  * beyond that: the site's seasonal pattern, from 2023 onwards
    (assets/weather_climatology.json, scripts/build_weather_climatology.py).

A day's factor comes from the measured rule (training work, 2026-10-10):
heavy rain (>= 25 mm) 0.57, the 7 days after it 0.52, other days 1.10,
divided by the site's yearly mean so the scale matches the seasonal table.
A project with no known location gets no weather - never a guess.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import requests

logger = logging.getLogger(__name__)

CLIMATOLOGY = Path(__file__).resolve().parents[1] / "assets" / "weather_climatology.json"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_SECONDS = 6 * 3600
_cache: Dict[str, Any] = {}


def _climatology() -> Optional[Dict[str, Any]]:
    if "clim" not in _cache:
        try:
            _cache["clim"] = json.loads(CLIMATOLOGY.read_text())
        except Exception as e:      # missing file: weather is simply off
            logger.warning("weather climatology unavailable: %s", e)
            _cache["clim"] = None
    return _cache["clim"]


def _live(station: str, lat: float, lng: float) -> Dict[date, float]:
    """Daily precipitation forecast (mm) for the next 16 days, cached."""
    key = f"live:{station}"
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    out: Dict[date, float] = {}
    try:
        r = requests.get(FORECAST_URL, params={
            "latitude": lat, "longitude": lng, "daily": "precipitation_sum",
            "timezone": "auto", "forecast_days": 16, "past_days": 7}, timeout=8)
        r.raise_for_status()
        d = r.json().get("daily") or {}
        for day, mm in zip(d.get("time") or [], d.get("precipitation_sum") or []):
            out[date.fromisoformat(day)] = float(mm or 0)
    except Exception as e:
        logger.warning("live weather forecast unavailable for %s, seasonal pattern only: %s", station, e)
    _cache[key] = (time.time(), out)
    return out


def site_factor(project_id: str, today: Optional[date] = None) -> Optional[Dict[str, Any]]:
    """{"factor": day -> speed factor, "station", "live_until", "source"} for
    a project, or None when its location is not known."""
    clim = _climatology()
    if not clim:
        return None
    station = (clim.get("projects") or {}).get(project_id)
    st = (clim.get("stations") or {}).get(station or "")
    if not st:
        return None
    rule = clim["rule"]
    f_heavy, f_after, f_norm = (rule["factors"][k] for k in ("heavy", "after_heavy", "normal"))
    doy = st["factor_by_day_of_year"]
    raw_mean = st.get("raw_mean") or 1.0
    live = _live(station, st["lat"], st["lng"]) if st.get("lat") is not None else {}
    heavy_days = sorted(d for d, mm in live.items() if mm >= rule["heavy_mm"])
    live_until = max(live) if live else None

    def factor(d: date) -> float:
        if live_until and d <= live_until and d in live:
            if live[d] >= rule["heavy_mm"]:
                raw = f_heavy
            elif any(0 < (d - h).days <= rule["after_days"] for h in heavy_days):
                raw = f_after
            else:
                raw = f_norm
            return raw / raw_mean
        return doy[min(d.timetuple().tm_yday, len(doy)) - 1]

    today = today or date.today()
    upcoming_heavy = [h for h in heavy_days if h >= today]
    return {
        "factor": factor, "station": station,
        "live_until": live_until.isoformat() if live_until else None,
        "source": ("live forecast to " + live_until.strftime("%d-%b") + ", then seasonal pattern")
                  if live_until else "seasonal pattern (live forecast unavailable)",
        "heavy_rain_ahead": [h.isoformat() for h in upcoming_heavy],
        "monsoon_months": [int(m) for m, v in (st.get("heavy_rain_days_per_month") or {}).items() if v >= 0.5],
    }


def factor_between(wx: Callable[[date], float], start: date, end: date) -> float:
    """Average speed factor over a period (for display)."""
    days = max(1, (end - start).days)
    return sum(wx(start + timedelta(days=i)) for i in range(days)) / days
