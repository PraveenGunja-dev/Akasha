"""Backtest of Advanced AI planning on finished work (read-only).

    backend\\venv\\Scripts\\python.exe backend\\scripts\\backtest_advanced_planning.py

For every block stage that is finished, on a project with an assigned
baseline, the forecast the plan would have made is compared with what
actually happened:

  1. Duration: the plan's method - torque tube / bracing / purlin from the
     project's OTHER finished blocks (leave-one-block-out), the rest from the
     P6 baseline - against trusting the baseline everywhere and against
     "baseline x slowness factor" learned from other projects.
  2. Weather: the same, with the season's speed factor over the stage's
     actual window (observed daily rain at the site, the measured rule), and
     whether stages that ran through wet weather really took longer.
  3. FTC: modules finished + the measured gap to charging (learned from other
     projects) against each block's actual FTC.

Needs the daily weather extract (training_model/data/raw/weather_daily.csv.gz)
for part 2; parts 1 and 3 read only the database.
"""
import json
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import logging  # noqa: E402
logging.disable(logging.CRITICAL)

from database import SessionLocal  # noqa: E402
from services import advanced_planning as ap  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CLIM = json.loads((ROOT / "backend" / "assets" / "weather_climatology.json").read_text())


def observed_factor_by_station():
    """station -> {day: factor} from observed rain, same rule and scale as the plan."""
    import pandas as pd
    path = ROOT / "training_model" / "data" / "raw" / "weather_daily.csv.gz"
    if not path.exists():
        return {}
    wx = pd.read_csv(path, parse_dates=["date"])
    rule = CLIM["rule"]
    out = {}
    for st, g in wx.groupby("station"):
        g = g.set_index("date").sort_index()
        heavy = g.precipitation_sum.fillna(0) >= rule["heavy_mm"]
        after = heavy.shift(1, fill_value=False).rolling(rule["after_days"], min_periods=1).max().astype(bool) & ~heavy
        f = pd.Series(rule["factors"]["normal"], index=g.index)
        f[after] = rule["factors"]["after_heavy"]
        f[heavy] = rule["factors"]["heavy"]
        f = f / CLIM["stations"].get(st, {}).get("raw_mean", f.mean())
        out[st] = {d.date(): v for d, v in f.items()}
    return out


def mae(xs):
    return round(mean(abs(x) for x in xs), 1) if xs else None


def med_abs(xs):
    return round(median(abs(x) for x in xs), 1) if xs else None


def main():
    db = SessionLocal()
    data = ap._load(db, None)
    obs = observed_factor_by_station()

    # Per project, per stage: actual/baseline ratios of finished blocks.
    ratios = defaultdict(lambda: defaultdict(list))
    samples = []          # (pid, stage, base_days, actual_days, start, finish)
    ftc_samples = []      # (pid, module_finish, ftc_actual)
    for pid, p in data.items():
        if not p.get("baseline"):
            continue
        for b in p["blocks"].values():
            for k in ap.STAGE_KEYS:
                a = b.get(k)
                if not a or not a["actual_finish"]:
                    continue
                act = ap._span(a["actual_start"], a["actual_finish"])
                base = ap._span(a["baseline_start"], a["baseline_finish"])
                if act and base:
                    ratios[pid][k].append(act / base)
                    samples.append((pid, k, base, act, a["actual_start"], a["actual_finish"]))
            m, f = b.get("module"), (b.get("_ftc") or {})
            if m and m["actual_finish"] and f.get("actual"):
                ftc_samples.append((pid, m["actual_finish"], f["actual"]))

    def factor_without(pid, k):
        per = [median(v[k]) for q, v in ratios.items() if q != pid and len(v[k]) >= 3]
        return median(per) if per else 1.0

    print(f"Finished block-stages with a baseline: {len(samples)} on {len({s[0] for s in samples})} projects")
    print("\n1. DURATION - error in days (mean absolute), forecast vs actual")
    own = defaultdict(list)
    for s_ in samples:
        own[(s_[0], s_[1])].append(s_)

    def plan_method(s_):
        pid, k, base, act, start, _ = s_
        others = [x[3] for x in own[(pid, k)] if x[4] != start]
        if k in ap.OWN_HISTORY_STAGES and len(others) >= ap.MIN_SAMPLES:
            return median(others)
        return base

    print(f"   {'stage':14s} {'n':>5s} {'trust baseline':>15s} {'baseline x factor':>18s} {'PLAN METHOD':>12s}   (mean / median abs error)")
    tot = defaultdict(list)
    for k in ap.STAGE_KEYS:
        rows = [s_ for s_ in samples if s_[1] == k]
        e = {"b": [s_[3] - s_[2] for s_ in rows],
             "f": [s_[3] - s_[2] * factor_without(s_[0], k) for s_ in rows],
             "p": [s_[3] - plan_method(s_) for s_ in rows]}
        for m, v in e.items():
            tot[m] += v
        print(f"   {k:14s} {len(rows):5d} " + " ".join(f"{mae(e[m]):>5}/{med_abs(e[m]):<5}" .rjust(w) for m, w in (("b", 15), ("f", 18), ("p", 12))))
    print(f"   {'ALL':14s} {len(samples):5d} " + " ".join(f"{mae(tot[m]):>5}/{med_abs(tot[m]):<5}".rjust(w) for m, w in (("b", 15), ("f", 18), ("p", 12))))

    print("\n2. WEATHER - stages at located sites, observed rain over each actual window")
    located = [s for s in samples if CLIM["projects"].get(s[0]) in obs]
    wet, dry, e_plain, e_wx = [], [], [], []
    for pid, k, base, act, start, finish in located:
        f_obs = obs[CLIM["projects"][pid]]
        days = [f_obs.get(start + timedelta(days=i)) for i in range((finish - start).days + 1)]
        days = [d for d in days if d is not None]
        if not days:
            continue
        w = mean(days)                       # <1 = a wetter-than-average window
        ratio = act / base
        (wet if w < 0.97 else dry).append(ratio)
        pred = base * factor_without(pid, k)
        e_plain.append(act - pred)
        e_wx.append(act - pred / w)
    print(f"   stages with weather data: {len(e_plain)}")
    if wet and dry:
        print(f"   wetter-than-average windows: {len(wet)} stages, took {median(wet):.2f}x baseline (median)")
        print(f"   other windows:               {len(dry)} stages, took {median(dry):.2f}x baseline (median)")
    print(f"   error without weather {mae(e_plain)} d, with observed weather {mae(e_wx)} d")
    # The fair test: each stage against the same project's other blocks of the
    # same stage, by the month it started (removes the project mix).
    rel = defaultdict(list)
    for (pid, k), xs in own.items():
        if pid not in CLIM["projects"] or len(xs) < 3:
            continue
        m = median(x[3] for x in xs)
        for x in xs:
            rel[x[4].month].append(x[3] / m)
    print("   same-project duration by START month (1.00 = that project's usual):")
    print("   " + "  ".join(f"{['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][mo-1]} "
                         f"{median(rel[mo]):.2f}" for mo in range(1, 13) if rel[mo]))

    print("\n3. FTC - block charged vs modules finished + measured gap (other projects)")
    by_pid = defaultdict(list)
    for pid, mf, fa in ftc_samples:
        by_pid[pid].append((fa - mf).days)
    errs = []
    for pid, mf, fa in ftc_samples:
        others = [median(v) for q, v in by_pid.items() if q != pid and len(v) >= 3]
        lag = median(others) if others else 0
        errs.append((fa - (mf + timedelta(days=round(lag)))).days)
    if errs:
        within = sum(1 for e in errs if abs(e) <= 30) / len(errs) * 100
        print(f"   blocks: {len(errs)} on {len(by_pid)} projects; median gap modules->FTC "
              f"{median([g for v in by_pid.values() for g in v])} d")
        print(f"   error mean abs {mae(errs)} d, median {median(errs)} d, within 30 d: {within:.0f}%")


if __name__ == "__main__":
    main()
