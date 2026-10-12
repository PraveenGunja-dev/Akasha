"""Build backend/assets/weather_climatology.json - the seasonal site-speed
factor used by Advanced AI planning's weather toggle.

    backend\\venv\\Scripts\\python.exe backend\\scripts\\build_weather_climatology.py

Input (from the training extract, training_model/pipelines/extract_weather.py):
  training_model/data/raw/weather_daily.csv.gz   daily rain per station, Open-Meteo archive
  training_model/data/raw/project_location.csv   project -> station (pooling substation)

Site output measured against rain (training work, 2026-10-10, P6 weekly
progress vs daily rain at the project's station):
  heavy-rain day (>= 25 mm)          0.57 x a normal day
  the 7 days after a heavy-rain day  0.52 x
  every other day                    1.10 x
For each station and day of the year: the chance of each kind of day over
the years on record -> expected factor, then divided by the station's yearly
mean, so 1.0 = an average day. Forecast durations already carry average
weather (they are measured on finished blocks); the toggle only adds or
removes the difference a wetter or drier stretch makes.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "training_model" / "data" / "raw"
OUT = ROOT / "backend" / "assets" / "weather_climatology.json"

HEAVY_MM = 25.0
AFTER_DAYS = 7
FACTORS = {"heavy": 0.57, "after_heavy": 0.52, "normal": 1.10}


def main() -> None:
    wx = pd.read_csv(RAW / "weather_daily.csv.gz", parse_dates=["date"])
    loc = pd.read_csv(RAW / "project_location.csv").dropna(subset=["station"]).drop_duplicates("project_id")
    stations = {}
    for st, g in wx.groupby("station"):
        g = g.set_index("date").sort_index()
        rain = g.precipitation_sum.fillna(0)
        heavy = rain >= HEAVY_MM
        after = heavy.shift(1, fill_value=False).rolling(AFTER_DAYS, min_periods=1).max().astype(bool) & ~heavy
        factor = pd.Series(FACTORS["normal"], index=g.index)
        factor[after] = FACTORS["after_heavy"]
        factor[heavy] = FACTORS["heavy"]
        doy = factor.groupby(factor.index.dayofyear).mean().reindex(range(1, 367))
        # smooth over a week either side: three years is a small sample per day
        doy = pd.concat([doy.iloc[-7:], doy, doy.iloc[:7]]).rolling(15, center=True, min_periods=1).mean().iloc[7:-7]
        raw_mean = float(doy.mean())
        doy = (doy / raw_mean).round(3)
        heavy_days = heavy.groupby(heavy.index.month).mean() * 30.4
        stations[st] = {
            "factor_by_day_of_year": doy.tolist(),
            # a live forecast day's raw factor is divided by this, the same scale
            "raw_mean": round(raw_mean, 4),
            "heavy_rain_days_per_month": {int(m): round(v, 1) for m, v in heavy_days.items()},
            "years": f"{g.index.min().date()} to {g.index.max().date()}",
        }
        lat = loc.loc[loc.station == st, "lat"]
        lng = loc.loc[loc.station == st, "lng"]
        if len(lat):
            stations[st].update(lat=float(lat.iloc[0]), lng=float(lng.iloc[0]))
    projects = {r.project_id: r.station for r in loc.itertuples() if r.station in stations}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "built": date.today().isoformat(),
        "source": "Open-Meteo archive, daily precipitation at each project's pooling substation",
        "rule": {"heavy_mm": HEAVY_MM, "after_days": AFTER_DAYS, "factors": FACTORS},
        "stations": stations, "projects": projects,
    }, indent=1))
    print(f"{OUT}: {len(stations)} stations, {len(projects)} projects located")
    for st, v in stations.items():
        f = v["factor_by_day_of_year"]
        print(f"  {st}: min {min(f):.2f} (day {f.index(min(f)) + 1}), max {max(f):.2f}; heavy days/month {v['heavy_rain_days_per_month']}")


if __name__ == "__main__":
    main()
