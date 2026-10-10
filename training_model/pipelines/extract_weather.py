"""
Step 1c - daily weather history at each project's location (Open-Meteo archive,
free, no key - the same provider the app's live weather uses).

    training_model\\.venv\\Scripts\\python.exe training_model\\pipelines\\extract_weather.py

Location = the project's pooling station from the transmission data (KPS-1/2/3
-> reference/substations_dms.tsv). A Khavda project with no transmission link
gets the Khavda centre (mean of KPS-I/II/III, all within ~20 km), labelled as
such. A project with no known location gets NO weather - never a guess.

Writes data/raw/project_location.csv and weather_daily.csv.gz.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import RAW, ROOT  # noqa: E402

REF = ROOT / "reference"
START = date(2023, 1, 1)
DAILY = "precipitation_sum,rain_sum,wind_speed_10m_max,wind_gusts_10m_max,temperature_2m_max"
KPS_NAME = {"KPS-1": "KPS-I", "KPS-2": "KPS-II", "KPS-3": "KPS-III"}


def dms(s: str) -> float:
    d, m, sec, hemi = re.match(r"(\d+)°(\d+)′([\d.]+)″([NSEW])", s.strip()).groups()
    v = int(d) + int(m) / 60 + float(sec) / 3600
    return -v if hemi in "SW" else v


def substations() -> pd.DataFrame:
    s = pd.read_csv(REF / "substations_dms.tsv", sep="\t")
    s["lat"], s["lng"] = s.lat_dms.map(dms).round(5), s.lng_dms.map(dms).round(5)
    s.to_csv(REF / "substations.csv", index=False)
    return s.set_index("substation")


def locate(kps_df: pd.DataFrame, subs: pd.DataFrame) -> pd.DataFrame:
    khavda = subs.loc[["KPS-I", "KPS-II", "KPS-III"], ["lat", "lng"]].mean()
    rows = []
    for r in kps_df.itertuples():
        kps = [k for k in str(r.kps or "").split(",") if k in KPS_NAME]
        if kps:
            # Several stations: the first listed is the main evacuation point;
            # they are all within ~20 km, so the weather is the same field.
            st = KPS_NAME[kps[0]]
            rows.append((r.project_id, st, subs.at[st, "lat"], subs.at[st, "lng"], "transmission link"))
        elif "khavda" in str(r.cluster or "").lower():
            rows.append((r.project_id, "Khavda centre", round(khavda.lat, 5), round(khavda.lng, 5),
                         "cluster (no transmission link)"))
        else:
            rows.append((r.project_id, None, None, None, "unknown - add its pooling substation"))
    return pd.DataFrame(rows, columns=["project_id", "station", "lat", "lng", "located_by"])


def fetch(lat: float, lng: float) -> pd.DataFrame:
    end = date.today() - timedelta(days=6)              # the archive lags ~5 days
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lng, "start_date": START.isoformat(),
        "end_date": end.isoformat(), "daily": DAILY, "timezone": "Asia/Kolkata"})
    with urllib.request.urlopen(url, timeout=120) as resp:
        d = json.load(resp)["daily"]
    return pd.DataFrame(d).rename(columns={"time": "date"})


def main():
    subs = substations()
    loc = locate(pd.read_csv(RAW / "project_kps.csv.gz"), subs)
    loc.to_csv(RAW / "project_location.csv", index=False)
    print(loc.located_by.value_counts().to_string())
    frames = []
    for st, g in loc.dropna(subset=["station"]).groupby("station"):
        w = fetch(g.lat.iloc[0], g.lng.iloc[0])
        w["station"] = st
        frames.append(w)
        print(f"  {st}: {len(w)} days, rain days (>=5mm) {int((w.precipitation_sum >= 5).sum())}")
    pd.concat(frames).to_csv(RAW / "weather_daily.csv.gz", index=False)


if __name__ == "__main__":
    main()
