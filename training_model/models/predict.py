"""
Step 5 - forecast every open block milestone with the latest registered model.

    training_model\\.venv\\Scripts\\python.exe training_model\\models\\predict.py

Writes registry/ftc_slip/<version>/forecast.csv: for each open milestone,
P20 / P50 / P80 forecast dates and the three inputs that moved its P50 most,
in plain words, with the value that drove them (the "why").
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATASETS, QUANTILES, REGISTRY  # noqa: E402
from models.train_ftc import CAT_COLS, _cat_text  # noqa: E402

# Plain-language name of every model input, for the "why" column.
LABELS = {
    "days_to_baseline": "Days left to the P6 baseline date",
    "baseline_month": "Month the baseline falls in",
    "blk_done": "Block activities finished", "blk_due": "Block activities due by now (baseline)",
    "blk_sv": "Block progress vs baseline", "blk_started": "Block activities started",
    "blk_piling_done": "Piling finished", "blk_mms_done": "MMS erection finished",
    "blk_module_done": "Module installation finished", "blk_idt_done": "IDT works finished",
    "blk_cable_done": "Cabling finished", "blk_scada_done": "SCADA finished",
    "blk_slip_so_far": "How late this block's finished work ran (median days)",
    "blk_overdue_n": "Block activities past their baseline and still open",
    "blk_overdue_days_max": "Longest overdue block activity (days)",
    "module_installation_done": "Module installation milestone done",
    "ftc_application_done": "FTC application submitted", "ftc_approval_done": "FTC approval received",
    "prj_done": "Project activities finished", "prj_due": "Project activities due by now",
    "prj_sv": "Project progress vs baseline",
    "prj_blocks_charged": "Blocks of this project already charged",
    "prj_ftc_slip_mean": "Earlier blocks' FTC delay (mean days)",
    "prj_ftc_slip_last": "Last charged block's FTC delay (days)",
    "prj_n_blocks": "Blocks in the project", "block_ftc_rank": "Block's place in the FTC sequence",
    "capacity_mwdc": "Project capacity (MWdc)", "category": "Category", "cluster": "Cluster",
    "mms_type": "MMS type", "source_of_origin": "Module source",
    "lta_gap_days": "LTA date minus baseline (days)", "scod_gap_days": "SCOD minus baseline (days)",
    "sup_ordered_frac": "Project modules ordered (share of capacity)",
    "sup_received_frac": "Project modules received (share of capacity)",
    "sup_import_share": "Share of ordered modules imported", "kind": "Milestone type",
}
PCT = {"blk_done", "blk_due", "blk_sv", "blk_started", "blk_piling_done", "blk_mms_done",
       "blk_module_done", "blk_idt_done", "blk_cable_done", "blk_scada_done", "prj_done",
       "prj_due", "prj_sv", "sup_ordered_frac", "sup_received_frac", "sup_import_share"}


def latest_model():
    versions = sorted((REGISTRY / "ftc_slip").glob("v*"))
    if not versions:
        raise SystemExit("No registered model - run models/train_ftc.py first.")
    d = versions[-1]
    return d, json.loads((d / "meta.json").read_text())


def load_models(d, meta):
    if meta["algorithm"] == "catboost":
        from catboost import CatBoostRegressor
        out = {}
        for q in QUANTILES:
            m = CatBoostRegressor()
            m.load_model(str(d / f"{q}.cbm"))
            out[q] = m
        return out
    import lightgbm as lgb
    return {q: lgb.Booster(model_file=str(d / f"{q}.txt")) for q in QUANTILES}


def fmt(feature, value):
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "unknown"
    if feature in PCT:
        return f"{value * 100:.0f}%"
    if feature.endswith("_done") and feature not in PCT:
        return "yes" if value >= 1 else "no"
    if isinstance(value, (int, float, np.floating)):
        return f"{value:.0f}"
    return str(value)


def main():
    d, meta = latest_model()
    live = pd.read_csv(DATASETS / "live.csv.gz")
    cols, cats = meta["features"], meta["categories"]
    X = live[cols].copy()
    for c in CAT_COLS:
        v = X[c].fillna("NA").astype(str)
        X[c] = pd.Categorical(v.where(v.isin(set(cats[c])), "NA"), categories=cats[c])
    models = load_models(d, meta)
    algo = meta["algorithm"]
    preds = {}
    for q, m in models.items():
        preds[q] = m.predict(_cat_text(X)) if algo == "catboost" else m.predict(X)
    cal = meta.get("calibration", {}).get("offsets")
    if cal:
        # Calibrated range (models/calibrate.py): P50 plus the measured spread
        # of the model's errors on unseen projects, for this horizon.
        from models.train_ftc import bucket
        off = [cal.get(bucket(h), cal["all"]) for h in live.days_to_baseline]
        p20 = preds["p50"] + np.array([o["p20"] for o in off])
        p80 = preds["p50"] + np.array([o["p80"] for o in off])
        stacked = np.vstack([p20, preds["p50"], p80])
    else:
        # Uncalibrated: quantile models trained separately; enforce order.
        stacked = np.sort(np.vstack([preds["p20"], preds["p50"], preds["p80"]]), axis=0)
    base = pd.to_datetime(live.baseline_finish)
    out = live[["milestone_key", "project_id", "block", "kind", "activity_id", "activity_name",
                "cutoff_date", "baseline_finish", "days_to_baseline"]].copy()
    for i, q in enumerate(("p20", "p50", "p80")):
        out[f"slip_{q}"] = stacked[i].round().astype(int)
        out[f"forecast_{q}"] = (base + pd.to_timedelta(stacked[i].round(), unit="D")).dt.date

    # Why: each input's contribution to the P50 forecast.
    if algo == "catboost":
        from catboost import Pool
        full = models["p50"].get_feature_importance(Pool(_cat_text(X), cat_features=CAT_COLS),
                                                    type="ShapValues")
    else:
        full = models["p50"].predict(X, pred_contrib=True)
    contrib, base_slip = full[:, :-1], full[:, -1]
    reasons = []
    for i in range(len(live)):
        top = np.argsort(-np.abs(contrib[i]))[:3]
        reasons.append(" | ".join(
            f"{LABELS.get(cols[j], cols[j])}: {fmt(cols[j], live.iloc[i][cols[j]])} "
            f"({'+' if contrib[i, j] >= 0 else '-'}{abs(contrib[i, j]):.0f}d)" for j in top))
    # The reasons explain the difference from a typical block, so the typical
    # block's slip is the starting point of every explanation.
    out["typical_slip_days"] = base_slip.round().astype(int)
    out["why"] = reasons
    # Only horizons the model was tested on are vouched for (config.HORIZONS).
    from config import HORIZONS
    lo, hi = min(HORIZONS), max(HORIZONS)
    out["confidence"] = np.where(live.days_to_baseline.between(lo, hi), "tested",
                                 f"beyond tested range ({lo}..{hi} days)")
    out["model_version"] = meta["version"]
    out.to_csv(d / "forecast.csv", index=False)
    ftc = out[out.kind == "ftc"]
    print(f"{len(out)} open milestones forecast ({len(ftc)} block FTCs) with {meta['version']} ({algo})")
    print(ftc.head(5)[["project_id", "block", "baseline_finish", "forecast_p20", "forecast_p50",
                       "forecast_p80", "why"]].to_string(index=False))


if __name__ == "__main__":
    main()
