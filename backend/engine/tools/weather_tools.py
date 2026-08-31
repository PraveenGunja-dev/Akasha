"""
Akasha AI Agent Tool — Weather Forecast

Provides the AI chatbot agent with the ability to query real-time Open-Meteo
weather forecasts for project sites to explain weather-driven delays.

Tool: weather_get_forecast
  - Resolves project site coordinates
  - Fetches 14-day rainfall and wind data
  - Returns monsoon and wind severity classifications
"""

import logging
from typing import Optional

from engine.intelligence.weather_intel import (
    _resolve_coordinates,
    _fetch_weather,
)

logger = logging.getLogger(__name__)


WEATHER_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "weather_get_forecast",
        "description": (
            "Fetch the live 14-day weather forecast for a project site, "
            "including expected rainfall, wind speeds, and productivity impact. "
            "Use this tool when investigating delays that might be caused by "
            "monsoon, waterlogging, or severe winds. Available for most major "
            "project sites (Khavda, Bhuj, Bhadla, Fatehgarh, etc.)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "project_name": {
                    "type": "string",
                    "description": "The project name (e.g. 'Khavda', 'Bhuj', 'Bhadla')"
                }
            },
            "required": ["project_name"],
        },
    },
}


def weather_get_forecast(project_name: str) -> dict:
    """
    AI Agent tool: fetch and summarize site weather conditions.
    """
    coords = _resolve_coordinates(project_name)
    if not coords:
        return {
            "status": "unsupported",
            "message": f"Site coordinates are not available for '{project_name}'. Cannot fetch weather.",
        }

    weather_data = _fetch_weather(coords["lat"], coords["lng"])
    if not weather_data or "daily" not in weather_data:
        return {
            "status": "error",
            "message": f"Failed to fetch weather data for '{project_name}' from Open-Meteo API.",
        }

    daily = weather_data["daily"]
    precip = daily.get("precipitation_sum", [])
    wind = daily.get("wind_speed_10m_max", [])

    avg_rain = sum(precip) / max(len(precip), 1)
    max_rain = max(precip) if precip else 0
    max_wind_speed = max(wind) if wind else 0
    rain_days = sum(1 for p in precip if p > 5)

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

    lost_days_rain = sum(1 for p in precip if p > 20)
    lost_days_wind = sum(1 for w in wind if w > 40)
    total_lost_days = min(lost_days_rain + lost_days_wind, 14)

    return {
        "status": "success",
        "project": project_name,
        "site_coords": coords,
        "forecast_period": "Next 14 days",
        "avg_rainfall_mm_per_day": round(avg_rain, 1),
        "max_rainfall_mm": round(max_rain, 1),
        "rain_days_over_5mm": rain_days,
        "max_wind_speed_kmh": round(max_wind_speed, 1),
        "monsoon_severity_classification": monsoon_severity,
        "wind_severity_classification": wind_severity,
        "estimated_lost_working_days": total_lost_days,
        "note": (
            "Use this data to explain weather-driven delays. 'Severe' or 'Heavy' "
            "monsoons cause severe waterlogging and halt civil works (piling, foundations). "
            "High winds halt crane operations and module mounting."
        ),
    }
