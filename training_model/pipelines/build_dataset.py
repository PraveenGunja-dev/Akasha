"""
Step 2 - build the block-level milestone dataset with point-in-time features.

    training_model\\.venv\\Scripts\\python.exe training_model\\pipelines\\build_dataset.py

One row = a MONTHLY REVIEW of one block milestone: "on the 1st of the month,
with the P6 plan in force that day, what did we know, and how late did it
actually finish?". Every feature is what a planner could have known on that
review date T:
  - a P6 activity counts as done only if its actual finish <= T;
  - the plan is the latest stored baseline TAKEN on or before T (P6 DataDate),
    never a later re-baseline that already knew how the work went;
  - a PO counts from its PO date, a receipt from its GR date;
  - weather is what had fallen by T, plus the climatology of the coming
    months computed WITHOUT the target year's actual rain.

Target: slip days = actual finish - the planned finish in force at T.

Outputs data/datasets/train.csv.gz (completed milestones) and live.csv.gz
(open milestones as of each project's P6 data date, for the forecast).
"""
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATASETS, HORIZONS, RAW, TARGET_KINDS  # noqa: E402

H_MIN, H_MAX = min(HORIZONS), max(HORIZONS)   # review window around the planned date
REVIEW_LOOKBACK_DAYS = 420                    # oldest review considered before the finish
WET_MM, HEAVY_MM = 5.0, 25.0

FAMILIES = {"piling": "piling", "mms erection": "mms", "module installation": "module",
            "idt": "idt", "cable": "cable", "scada": "scada", "earthing": "earthing"}


def family(name: str) -> str:
    n = str(name).lower()
    return next((v for k, v in FAMILIES.items() if k in n), "other")


class SortedDates:
    """Count of dates <= T in O(log n) - the backbone of 'as of T' features."""

    def __init__(self, s):
        v = pd.to_datetime(pd.Series(s)).dropna().values.astype("datetime64[ns]")
        self.v = np.sort(v)
        self.n = len(self.v)

    def le(self, t) -> int:
        return int(np.searchsorted(self.v, np.datetime64(t, "ns"), side="right"))

    def between(self, a, b) -> int:            # (a, b]
        return self.le(b) - self.le(a)


# -- Loading ---------------------------------------------------------------------
def load():
    dt = ["baseline_start_date", "baseline_finish_date", "actual_start_date", "actual_finish_date"]
    acts = pd.read_csv(RAW / "p6_activities.csv.gz", parse_dates=dt)
    proj = pd.read_csv(RAW / "p6_projects.csv.gz", parse_dates=["data_date", "baseline_taken"])
    reg = pd.read_csv(RAW / "register.csv.gz", parse_dates=["lta_date", "manual_scod"])
    po = pd.read_csv(RAW / "module_po_lines.csv.gz", parse_dates=["document_date", "po_first_release"])
    rec = pd.read_csv(RAW / "module_receipts.csv.gz", parse_dates=["receipt_date", "dispatch_date"])
    links = pd.read_csv(RAW / "project_wbs.csv.gz")
    bls = pd.read_csv(RAW / "p6_baselines.csv.gz")
    bls["taken"] = pd.to_datetime(bls.data_date.str[:10])
    bacts = pd.read_csv(RAW / "p6_baseline_activities.csv.gz")
    bacts["planned_finish"] = pd.to_datetime(bacts.planned_finish.str[:19])
    loc = pd.read_csv(RAW / "project_location.csv")
    wx = pd.read_csv(RAW / "weather_daily.csv.gz", parse_dates=["date"])
    return acts, proj, reg, po, rec, links, bls, bacts, loc, wx


# -- Plan history (stored baselines) --------------------------------------------
def plan_history(acts, proj, bls, bacts):
    """(project, activity) -> [(taken, planned_finish)] sorted by taken, and
    (project, block) -> [(taken, SortedDates of planned finishes)] for 'due by T'."""
    b = bacts.merge(bls[["baseline_object_id", "taken"]], on="baseline_object_id")
    hist = defaultdict(list)
    for r in b[["project_object_id", "activity_id", "taken", "planned_finish"]].itertuples(index=False):
        if pd.notna(r.planned_finish):
            hist[(r.project_object_id, r.activity_id)].append((r.taken, r.planned_finish))
    # The live schedule's assigned baseline is a plan too, when we know when
    # it was taken.
    live = acts.merge(proj[["project_object_id", "baseline_taken"]], on="project_object_id")
    live = live[live.baseline_taken.notna() & live.baseline_finish_date.notna()]
    for r in live[["project_object_id", "activity_id", "baseline_taken", "baseline_finish_date"]].itertuples(index=False):
        hist[(r.project_object_id, r.activity_id)].append((r.baseline_taken, r.baseline_finish_date))
    for k in hist:
        hist[k] = sorted(set(hist[k]))
    b["block"] = b.name.str.extract(r"(?i)\bblock[\s\-_:]*0*(\d{1,3})\b", expand=False).astype(float)
    due = defaultdict(list)
    for (poid, blk, taken), g in b.dropna(subset=["block"]).groupby(["project_object_id", "block", "taken"]):
        due[(poid, blk)].append((taken, SortedDates(g.planned_finish), len(g)))
    for k in due:
        due[k].sort(key=lambda x: x[0])
    pdue = {}
    for (poid, taken), g in b.groupby(["project_object_id", "taken"]):
        pdue.setdefault(poid, []).append((taken, SortedDates(g.planned_finish), len(g)))
    for k in pdue:
        pdue[k].sort(key=lambda x: x[0])
    return hist, due, pdue


def in_force(entries, T):
    """Latest entry taken on or before T (entries sorted by taken)."""
    best = None
    for e in entries:
        if e[0] <= T:
            best = e
        else:
            break
    return best


# -- Weather ----------------------------------------------------------------------
class Weather:
    def __init__(self, wx, loc):
        self.station = dict(zip(loc.project_id, loc.station))
        self.daily = {}
        self.clim = {}
        for st, g in wx.groupby("station"):
            g = g.set_index("date").sort_index()
            self.daily[st] = g.precipitation_sum.fillna(0)
            g = g.assign(wet=(g.precipitation_sum >= WET_MM).astype(float), doy=g.index.dayofyear, yr=g.index.year)
            # Leave-one-year-out climatology: P(wet day) per day-of-year from the
            # OTHER years, so a window's own rain never informs its forecast.
            per_year = {}
            for y in g.yr.unique():
                other = g[g.yr != y].groupby("doy").wet.mean()
                per_year[y] = other.reindex(range(1, 367)).interpolate().bfill().ffill().values
            per_year["all"] = g.groupby("doy").wet.mean().reindex(range(1, 367)).interpolate().bfill().ffill().values
            self.clim[st] = per_year

    def features(self, pid, T):
        st = self.station.get(pid)
        if not isinstance(st, str) or st not in self.daily:
            return {"wx_rain_30d": np.nan, "wx_heavy_days_30d": np.nan,
                    "wx_wet_days_next60": np.nan, "wx_wet_days_next120": np.nan}
        d = self.daily[st]
        past = d[(d.index > T - pd.Timedelta(days=30)) & (d.index <= T)]
        out = {"wx_rain_30d": float(past.sum()), "wx_heavy_days_30d": int((past >= HEAVY_MM).sum())}
        for n in (60, 120):
            days = pd.date_range(T + pd.Timedelta(days=1), periods=n)
            tot = 0.0
            for day in days:
                c = self.clim[st].get(day.year, self.clim[st]["all"])
                tot += c[day.dayofyear - 1]
            out[f"wx_wet_days_next{n}"] = round(tot, 2)
        return out


# -- Supply (SAP, project level) ---------------------------------------------------
def supply_tables(proj, reg, po, rec, links):
    share = links.groupby(["project_id", "wbs_key"]).share.sum().reset_index()
    po = po.assign(po_date=po.document_date.fillna(po.po_first_release))
    ordered = po.merge(share, on="wbs_key")
    ordered["mw"] = ordered.ordered_mw * ordered.share
    received = rec[rec.receipt_date.notna()].merge(share.rename(columns={"share": "pshare"}), on="wbs_key")
    received["mw"] = received.mwp * received.pshare
    cap = reg.groupby("project_id").capacity_mwdc.sum()
    out = {}
    for pid in proj.project_id:
        o = ordered[ordered.project_id == pid].sort_values("po_date")
        r = received[received.project_id == pid].sort_values("receipt_date")
        out[pid] = {"cap": float(cap.get(pid, np.nan) or np.nan),
                    "o_dates": o.po_date.values.astype("datetime64[ns]"), "o_cum": o.mw.cumsum().values,
                    "o_import": (o.origin == "import").values, "o_mw": o.mw.values,
                    "r_dates": r.receipt_date.values.astype("datetime64[ns]"), "r_cum": r.mw.cumsum().values}
    return out


def cum_at(dates, cum, t):
    i = np.searchsorted(dates, np.datetime64(t, "ns"), side="right")
    return float(cum[i - 1]) if i > 0 else 0.0


# -- Build -----------------------------------------------------------------------------
def build():
    acts, proj, reg, po, rec, links, bls, bacts, loc, wx = load()
    acts = acts.merge(proj[["project_object_id", "project_id", "data_date"]], on="project_object_id")
    acts["family"] = acts.name.map(family)
    blocks = acts[acts.block.notna()]
    hist, due_hist, pdue_hist = plan_history(acts, proj, bls, bacts)
    weather = Weather(wx, loc)
    supply = supply_tables(proj, reg, po, rec, links)
    regp = reg.groupby("project_id").agg(
        capacity_mwdc=("capacity_mwdc", "sum"), category=("category", "first"),
        cluster=("cluster", "first"), mms_type=("mms_type", "first"),
        source_of_origin=("source_of_origin", "first"), lta_date=("lta_date", "min"),
        scod=("manual_scod", "min")).to_dict("index")

    block_idx = {}
    for (poid, b), g in blocks.groupby(["project_object_id", "block"]):
        fin = g[g.actual_finish_date.notna() & g.baseline_finish_date.notna()]
        block_idx[(poid, b)] = {
            "n": len(g), "done": SortedDates(g.actual_finish_date), "started": SortedDates(g.actual_start_date),
            "fam": {f: (SortedDates(x.actual_finish_date), len(x)) for f, x in g.groupby("family")},
            "acts": g[["activity_id", "actual_finish_date"]].values,
        }
    proj_idx = {poid: {"n": len(g), "done": SortedDates(g.actual_finish_date)}
                for poid, g in blocks.groupby("project_object_id")}
    chain = {(r.project_object_id, r.block, r.kind): r for r in
             blocks[blocks.kind.isin(TARGET_KINDS)].itertuples()}
    # Each charged block's FTC: (actual finish, its slip vs the plan in force
    # 30 days before it charged) - "how late this project's blocks run".
    ftc_hist = defaultdict(list)
    for r in blocks[(blocks.kind == "ftc") & blocks.actual_finish_date.notna()].itertuples():
        e = in_force(hist.get((r.project_object_id, r.activity_id), []), r.actual_finish_date - pd.Timedelta(days=30))
        if e is not None:
            ftc_hist[r.project_object_id].append((r.actual_finish_date, (r.actual_finish_date - e[1]).days))
    for k in ftc_hist:
        ftc_hist[k].sort()
    n_blocks = blocks.groupby("project_object_id").block.nunique()
    ctx = dict(block_idx=block_idx, proj_idx=proj_idx, chain=chain, ftc_hist=ftc_hist, supply=supply,
               regp=regp, n_blocks=n_blocks, hist=hist, due_hist=due_hist, pdue_hist=pdue_hist, weather=weather)

    targets = blocks[blocks.kind.isin(TARGET_KINDS)]
    train_rows, live_rows = [], []
    skipped = defaultdict(int)
    for t in targets.itertuples():
        plans = hist.get((t.project_object_id, t.activity_id), [])
        done = pd.notna(t.actual_finish_date)
        if not plans and not done and pd.notna(t.baseline_finish_date):
            # A live forecast only needs today's plan; when that baseline was
            # taken matters for training (leakage), not for forecasting.
            plans = [(t.data_date.normalize(), t.baseline_finish_date)]
        if not plans:
            skipped["no plan history"] += 1
            continue
        if done:
            first = max(plans[0][0], t.actual_finish_date - pd.Timedelta(days=REVIEW_LOOKBACK_DAYS))
            reviews = pd.date_range(first.to_period("M").to_timestamp() + pd.offsets.MonthBegin(1),
                                    t.actual_finish_date - pd.Timedelta(days=1), freq="MS")
        else:
            reviews = [t.data_date.normalize()]
        for T in reviews:
            if T > t.data_date:
                continue
            e = in_force(plans, T)
            if e is None:
                skipped["no plan in force"] += 1
                continue
            ref = e[1]
            h = (ref - T).days
            if done and not (H_MIN <= h <= H_MAX):
                continue
            row = features(t, T, ref, h, plans, ctx)
            if done:
                row["slip_days"] = (t.actual_finish_date - ref).days
                train_rows.append(row)
            else:
                live_rows.append(row)

    DATASETS.mkdir(parents=True, exist_ok=True)
    train, live = pd.DataFrame(train_rows), pd.DataFrame(live_rows)
    train.to_csv(DATASETS / "train.csv.gz", index=False)
    live.to_csv(DATASETS / "live.csv.gz", index=False)
    print(f"train rows {len(train)} from {train.milestone_key.nunique()} milestones / "
          f"{train.project_id.nunique()} projects; FTC: {train[train.kind == 'ftc'].milestone_key.nunique()} "
          f"blocks, {int((train.kind == 'ftc').sum())} reviews")
    print(f"live rows  {len(live)}; skipped: {dict(skipped)}")
    return train, live


def features(t, T, ref, h, plans, c):
    poid, b = t.project_object_id, t.block
    bi, pi = c["block_idx"][(poid, b)], c["proj_idx"][poid]
    Tn = np.datetime64(T, "ns")
    r = {"milestone_key": f"{poid}:{int(b)}:{t.kind}", "project_object_id": poid, "project_id": t.project_id,
         "block": int(b), "kind": t.kind, "activity_id": t.activity_id, "activity_name": t.name,
         "cutoff_date": T.date().isoformat(), "baseline_finish": pd.Timestamp(ref).date().isoformat(),
         "days_to_baseline": int(h), "baseline_month": pd.Timestamp(ref).month}

    # Block progress at T vs the plan in force at T.
    done = bi["done"].le(T) / bi["n"]
    e = in_force(c["due_hist"].get((poid, b), []), T)
    due = e[1].le(T) / e[2] if e else np.nan
    r.update(blk_done=done, blk_due=due, blk_sv=done - due if e else np.nan,
             blk_started=bi["started"].le(T) / bi["n"])
    for f in ("piling", "mms", "module", "idt", "cable", "scada"):
        sd = bi["fam"].get(f)
        r[f"blk_{f}_done"] = sd[0].le(T) / sd[1] if sd else np.nan
    # Overdue at T against the plan in force at T.
    od = []
    for aid, af in bi["acts"]:
        pe = in_force(c["hist"].get((poid, aid), []), T)
        if pe is not None and pe[1] <= T and (pd.isna(af) or af > T):
            od.append((T - pe[1]).days)
    r["blk_overdue_n"], r["blk_overdue_days_max"] = len(od), float(max(od)) if od else 0.0

    # Productivity at T: completions in the last 30 days vs the 30 before.
    d30, d60 = T - pd.Timedelta(days=30), T - pd.Timedelta(days=60)
    r["blk_pace_30d"] = bi["done"].between(d30, T) / bi["n"]
    r["blk_pace_prev30d"] = bi["done"].between(d60, d30) / bi["n"]
    r["prj_pace_30d"] = pi["done"].between(d30, T) / pi["n"]
    r["prj_pace_prev30d"] = pi["done"].between(d60, d30) / pi["n"]

    # P6 reliability: how often this milestone's planned date moved by T.
    known = [p for p in plans if p[0] <= T]
    fins = [p[1] for p in known]
    moves = [(b2 - a2).days for a2, b2 in zip(fins, fins[1:]) if abs((b2 - a2).days) > 3]
    r["plan_revisions"] = len(moves)
    r["plan_total_shift_days"] = (fins[-1] - fins[0]).days if len(fins) > 1 else 0
    r["plan_last_shift_days"] = moves[-1] if moves else 0

    for step in ("module_installation", "ftc_application", "ftc_approval"):
        ch = c["chain"].get((poid, b, step))
        r[f"{step}_done"] = np.nan if ch is None else float(
            pd.notna(ch.actual_finish_date) and ch.actual_finish_date <= T)

    # Project at T.
    r["prj_done"] = pi["done"].le(T) / pi["n"]
    pe = in_force(c["pdue_hist"].get(poid, []), T)
    r["prj_due"] = pe[1].le(T) / pe[2] if pe else np.nan
    r["prj_sv"] = r["prj_done"] - r["prj_due"] if pe else np.nan
    s = np.array([sl for af, sl in c["ftc_hist"].get(poid, []) if af <= T], dtype=float)
    r["prj_blocks_charged"] = len(s)
    r["prj_ftc_slip_mean"] = float(s.mean()) if len(s) else np.nan
    r["prj_ftc_slip_last"] = float(s[-1]) if len(s) else np.nan
    r["prj_n_blocks"] = int(c["n_blocks"].get(poid, 0))

    g = c["regp"].get(t.project_id, {})
    for col in ("capacity_mwdc", "category", "cluster", "mms_type", "source_of_origin"):
        r[col] = g.get(col)
    for col, name in (("lta_date", "lta_gap_days"), ("scod", "scod_gap_days")):
        r[name] = (g[col] - ref).days if pd.notna(g.get(col)) else np.nan

    sp = c["supply"].get(t.project_id)
    if sp and len(sp["o_dates"]) and sp["cap"] == sp["cap"] and sp["cap"]:
        r["sup_ordered_frac"] = cum_at(sp["o_dates"], sp["o_cum"], T) / sp["cap"]
        m = sp["o_dates"] <= Tn
        r["sup_import_share"] = float(sp["o_mw"][m & sp["o_import"]].sum() / sp["o_mw"][m].sum()) if m.any() else np.nan
        r["sup_received_frac"] = cum_at(sp["r_dates"], sp["r_cum"], T) / sp["cap"] if len(sp["r_dates"]) else np.nan
    else:
        r["sup_ordered_frac"] = r["sup_import_share"] = r["sup_received_frac"] = np.nan

    r.update(c["weather"].features(t.project_id, T))
    return r


if __name__ == "__main__":
    build()
