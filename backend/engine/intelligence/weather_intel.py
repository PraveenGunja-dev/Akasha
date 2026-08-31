"""
Akasha Intelligence Engine — Weather Intelligence

Fetches live weather data from Open-Meteo API using real project site coordinates
to assess weather impact on construction:
- Monsoon severity classification (Normal / Heavy / Severe)
- Wind alert classification (Normal / High)
- Productivity impact estimation
- Weather-specific insights for cross-domain correlation

Read-only: never modifies existing data.
"""

import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
# Real Project Site Coordinates
# (from SimulationLab.tsx SUBSTATION_COORDS)
# ══════════════════════════════════════════════════════════════

SITE_COORDINATES: Dict[str, Dict[str, float]] = {
    "khavda": {"lat": 24.024, "lng": 69.337},
    "bhuj": {"lat": 23.379, "lng": 69.592},
    "bhadla": {"lat": 27.618, "lng": 72.206},
    "fatehgarh": {"lat": 26.285, "lng": 71.100},
    "ramgarh": {"lat": 27.471, "lng": 70.494},
    "bikaner": {"lat": 28.373, "lng": 73.171},
    "rajasthan": {"lat": 27.0, "lng": 74.2},
    "gujarat": {"lat": 23.0, "lng": 72.5},
    "halvad": {"lat": 22.911, "lng": 71.231},
    "lakadia": {"lat": 23.394, "lng": 70.598},
    "banaskantha": {"lat": 24.090, "lng": 72.000},
    "sikar": {"lat": 27.612, "lng": 75.088},
    "mandvi": {"lat": 22.833, "lng": 69.355},
    "pirana": {"lat": 22.872, "lng": 72.557},
    "mandsaur": {"lat": 24.207, "lng": 75.171},
    "baiya": {"lat": 23.379, "lng": 69.592},
    "bandha": {"lat": 27.0, "lng": 74.2},
}


def _resolve_coordinates(project_name: str) -> Optional[Dict[str, float]]:
    """Resolve a project name to its site coordinates."""
    name_lower = (project_name or "").lower()
    for key, coords in SITE_COORDINATES.items():
        if key in name_lower:
            return coords
    return None


def _fetch_weather(lat: float, lng: float) -> Optional[Dict[str, Any]]:
    """Fetch 14-day weather forecast from Open-Meteo API."""
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lng}"
        f"&daily=precipitation_sum,wind_speed_10m_max,temperature_2m_max"
        f"&timezone=auto&forecast_days=14"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Open-Meteo API failed: {e}")
        return None


def analyze_weather(ctx: dict) -> dict:
    """
    Weather intelligence analysis for a project.

    Fetches real-time weather data for the project's site coordinates
    and assesses its impact on construction productivity.
    """
    project_name = ctx["project_name"]

    # ═══════════════════════════════════════════════════════
    # 1. RESOLVE SITE COORDINATES
    # ═══════════════════════════════════════════════════════
    coords = _resolve_coordinates(project_name)
    if not coords:
        return {
            "has_data": False,
            "health_score": None,
            "insights": [{
                "severity": "info",
                "domain": "weather",
                "title": f"No site coordinates for {project_name}",
                "description": "Cannot determine weather impact without known site location.",
                "impact": "Weather-driven delays cannot be assessed",
            }],
        }

    # ═══════════════════════════════════════════════════════
    # 2. FETCH LIVE WEATHER DATA
    # ═══════════════════════════════════════════════════════
    weather_data = _fetch_weather(coords["lat"], coords["lng"])
    if not weather_data or "daily" not in weather_data:
        return {
            "has_data": False,
            "health_score": None,
            "insights": [{
                "severity": "info",
                "domain": "weather",
                "title": "Weather data temporarily unavailable",
                "description": "Open-Meteo API did not return forecast data.",
                "impact": "Weather impact assessment deferred",
            }],
        }

    daily = weather_data["daily"]
    precip = daily.get("precipitation_sum", [])
    wind = daily.get("wind_speed_10m_max", [])
    temp = daily.get("temperature_2m_max", [])
    dates = daily.get("time", [])

    # ═══════════════════════════════════════════════════════
    # 3. CLASSIFY MONSOON & WIND SEVERITY
    # ═══════════════════════════════════════════════════════
    avg_rain = sum(precip) / max(len(precip), 1)
    max_rain = max(precip) if precip else 0
    max_wind_speed = max(wind) if wind else 0
    rain_days = sum(1 for p in precip if p > 5)  # Days with >5mm rain

    if avg_rain > 40:
        monsoon_severity = "Severe"
    elif avg_rain > 10:
        monsoon_severity = "Heavy"
    elif avg_rain > 2:
        monsoon_severity = "Light"
    else:
        monsoon_severity = "Normal"

    if max_wind_speed > 50:
        wind_severity = "Dangerous"
    elif max_wind_speed > 30:
        wind_severity = "High Alerts"
    else:
        wind_severity = "Normal"

    # ═══════════════════════════════════════════════════════
    # 4. ESTIMATE PRODUCTIVITY IMPACT
    # ═══════════════════════════════════════════════════════
    # Lost working days in the 14-day forecast
    lost_days_rain = sum(1 for p in precip if p > 20)  # Heavy rain = no work
    lost_days_wind = sum(1 for w in wind if w > 40)     # Crane ops unsafe
    total_lost_days = min(lost_days_rain + lost_days_wind, 14)
    productivity_factor = round((14 - total_lost_days) / 14 * 100, 1)

    # ═══════════════════════════════════════════════════════
    # 5. HEALTH SCORE
    # ═══════════════════════════════════════════════════════
    if monsoon_severity == "Normal" and wind_severity == "Normal":
        health_score = 95
    elif monsoon_severity == "Light" and wind_severity == "Normal":
        health_score = 85
    elif monsoon_severity == "Heavy":
        health_score = 50
    elif monsoon_severity == "Severe":
        health_score = 20
    elif wind_severity == "High Alerts":
        health_score = 60
    elif wind_severity == "Dangerous":
        health_score = 15
    else:
        health_score = 70

    # Adjust for cumulative lost days
    if total_lost_days >= 5:
        health_score = min(health_score, 30)
    elif total_lost_days >= 3:
        health_score = min(health_score, 50)

    # ═══════════════════════════════════════════════════════
    # 6. GENERATE INSIGHTS
    # ═══════════════════════════════════════════════════════
    insights = []

    if monsoon_severity in ("Heavy", "Severe"):
        insights.append({
            "severity": "high" if monsoon_severity == "Severe" else "medium",
            "domain": "weather",
            "title": f"{monsoon_severity} monsoon at {project_name} site",
            "description": (
                f"Average rainfall: {avg_rain:.1f}mm/day over next 14 days. "
                f"Peak: {max_rain:.1f}mm. Rain days: {rain_days}/14."
            ),
            "impact": (
                f"Estimated {lost_days_rain} working days lost to rain. "
                f"Waterlogging risk for piling and foundation activities."
            ),
        })

    if wind_severity != "Normal":
        insights.append({
            "severity": "high" if wind_severity == "Dangerous" else "medium",
            "domain": "weather",
            "title": f"{wind_severity}: Max wind {max_wind_speed:.0f} km/h at {project_name}",
            "description": (
                f"Wind speeds exceeding safe limits for crane operations and "
                f"module installation in the next 14 days."
            ),
            "impact": (
                f"Estimated {lost_days_wind} working days lost to high winds. "
                f"MMS erection and module mounting at risk."
            ),
        })

    if total_lost_days == 0 and monsoon_severity == "Normal":
        insights.append({
            "severity": "info",
            "domain": "weather",
            "title": f"Weather conditions favorable at {project_name}",
            "description": (
                f"No significant rain or wind expected over the next 14 days. "
                f"Avg rain: {avg_rain:.1f}mm, max wind: {max_wind_speed:.0f} km/h."
            ),
            "impact": "Full construction productivity expected — no weather-driven delays",
        })

    return {
        "has_data": True,
        "health_score": health_score,
        "site_coords": coords,
        "forecast_days": len(dates),
        "avg_rainfall_mm": round(avg_rain, 1),
        "max_rainfall_mm": round(max_rain, 1),
        "rain_days": rain_days,
        "max_wind_kmh": round(max_wind_speed, 1),
        "monsoon_severity": monsoon_severity,
        "wind_severity": wind_severity,
        "lost_working_days": total_lost_days,
        "productivity_factor_pct": productivity_factor,
        "insights": insights,
    }
