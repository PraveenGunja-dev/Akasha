"""
Step 3 - train and evaluate the block FTC slip model, then register it.

    training_model\\.venv\\Scripts\\python.exe training_model\\models\\train_ftc.py

Predicts slip days (actual finish - baseline finish) of a block milestone as
P20 / P50 / P80, so the forecast is a range, never a single confident date.

Evaluation is cross-validation GROUPED BY PROJECT: every score comes from
projects the model never saw. It is graded on FTC only and compared with
  - P6:    the baseline date itself (slip 0) - what the screen shows today
  - naive: this project's earlier blocks' mean FTC slip, else the training median
A model is only marked deployable where it beats both.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import (DATASETS, GRADED_KIND, HORIZON_BUCKETS, N_FOLDS, QUANTILES,  # noqa: E402
                    REGISTRY, SEED)

ID_COLS = ["milestone_key", "project_object_id", "project_id", "block", "activity_id",
           "activity_name", "cutoff_date", "baseline_finish", "slip_days"]
CAT_COLS = ["kind", "category", "cluster", "mms_type", "source_of_origin"]


def feature_cols(df):
    return [c for c in df.columns if c not in ID_COLS]


def prep(df, cols, cats=None):
    X = df[cols].copy()
    for c in CAT_COLS:
        X[c] = X[c].fillna("NA").astype(str)
        if cats is not None:
            known = set(cats[c])
            safe_cats = list(cats[c]) if "NA" in cats[c] else list(cats[c]) + ["NA"]
            X[c] = pd.Categorical(X[c].where(X[c].isin(known), "NA"), categories=safe_cats)
        else:
            X[c] = X[c].astype("category")
    return X


def bucket(h):
    for lo, hi, name in HORIZON_BUCKETS:
        if lo <= h <= hi:
            return name
    return "other"


# -- Models ------------------------------------------------------------------
def _cat_text(X):
    """CatBoost wants categoricals as text; a category unseen in training
    becomes "NA" rather than a missing value."""
    Xc = X.copy()
    for c in CAT_COLS:
        Xc[c] = Xc[c].astype(object).where(Xc[c].notna(), "NA").astype(str)
    return Xc


def fit_lgbm(X, y, alpha):
    import lightgbm as lgb
    params = {"objective": "quantile", "alpha": alpha, "learning_rate": 0.05, "num_leaves": 15,
              "min_data_in_leaf": 20, "feature_fraction": 0.8, "bagging_fraction": 0.8,
              "bagging_freq": 1, "lambda_l2": 1.0, "verbose": -1, "seed": SEED}
    return lgb.train(params, lgb.Dataset(X, y, categorical_feature=CAT_COLS), num_boost_round=300)


def fit_cat(X, y, alpha):
    from catboost import CatBoostRegressor
    m = CatBoostRegressor(loss_function=f"Quantile:alpha={alpha}", iterations=600, depth=5,
                          learning_rate=0.05, l2_leaf_reg=5, random_seed=SEED, verbose=0,
                          train_dir=str(DATASETS.parent / "catboost_info"))
    m.fit(_cat_text(X), y, cat_features=CAT_COLS)
    return m


def predict(kind, model, X):
    if kind == "catboost":
        return model.predict(_cat_text(X))
    return model.predict(X)


FITTERS = {"lightgbm": fit_lgbm, "catboost": fit_cat}


# -- Cross-validation ----------------------------------------------------------
def project_folds(projects, k):
    rng = np.random.default_rng(SEED)
    p = np.array(sorted(projects))
    rng.shuffle(p)
    return [set(p[i::k]) for i in range(k)]


def cross_validate(df):
    cols = feature_cols(df)
    out = []
    for i, test_p in enumerate(project_folds(df.project_id.unique(), N_FOLDS)):
        tr, te = df[~df.project_id.isin(test_p)], df[df.project_id.isin(test_p)]
        te = te[te.kind == GRADED_KIND]
        if te.empty:
            continue
        Xtr = prep(tr, cols)
        cats = {c: Xtr[c].cat.categories for c in CAT_COLS}
        Xte = prep(te, cols, cats)
        res = te[["milestone_key", "project_id", "days_to_baseline", "slip_days", "prj_ftc_slip_mean"]].copy()
        res["fold"] = i
        res["p6"] = 0.0
        med = tr[tr.kind == GRADED_KIND].slip_days.median()
        res["naive"] = te.prj_ftc_slip_mean.fillna(med).values
        for name, fit in FITTERS.items():
            for q, a in QUANTILES.items():
                res[f"{name}_{q}"] = predict(name, fit(Xtr, tr.slip_days, a), Xte)
        out.append(res)
        print(f"  fold {i}: {len(te)} FTC rows from {te.project_id.nunique()} unseen projects")
    return pd.concat(out)


def score(cv):
    cv = cv.copy()
    cv["bucket"] = cv.days_to_baseline.map(bucket)
    rows = []
    for b, g in [("all", cv)] + list(cv.groupby("bucket")):
        r = {"horizon": b, "rows": len(g), "blocks": g.milestone_key.nunique()}
        for m in ["p6", "naive", "lightgbm_p50", "catboost_p50"]:
            e = (g[m] - g.slip_days).abs()
            r[f"{m}_mae"] = round(e.mean(), 1)
            r[f"{m}_within30"] = round((e <= 30).mean() * 100, 1)
        for name in FITTERS:
            inside = (g.slip_days >= g[f"{name}_p20"]) & (g.slip_days <= g[f"{name}_p80"])
            r[f"{name}_band_cov"] = round(inside.mean() * 100, 1)        # target ~60%
            r[f"{name}_p80_cov"] = round((g.slip_days <= g[f"{name}_p80"]).mean() * 100, 1)  # ~80%
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(DATASETS / "train.csv.gz")
    print(f"dataset: {len(df)} rows, {df.project_id.nunique()} projects, "
          f"{(df.kind == GRADED_KIND).sum()} FTC rows")
    cv = cross_validate(df)
    table = score(cv)
    pd.set_option("display.width", 250)
    print(table.to_string(index=False))

    overall = table[table.horizon == "all"].iloc[0]
    best = min(FITTERS, key=lambda n: overall[f"{n}_p50_mae"])
    beats = overall[f"{best}_p50_mae"] < min(overall.p6_mae, overall.naive_mae)

    # Final model on all data, registered with its evaluation.
    cols = feature_cols(df)
    X = prep(df, cols)
    version = datetime.now().strftime("v%Y%m%d_%H%M")
    out = REGISTRY / "ftc_slip" / version
    out.mkdir(parents=True, exist_ok=True)
    for q, a in QUANTILES.items():
        m = FITTERS[best](X, df.slip_days, a)
        if best == "catboost":
            m.save_model(str(out / f"{q}.cbm"))
        else:
            m.save_model(str(out / f"{q}.txt"))
    meta = {
        "version": version, "trained_at": datetime.now().isoformat(timespec="seconds"),
        "algorithm": best, "deployable": bool(beats), "features": cols, "categorical": CAT_COLS,
        "categories": {c: list(X[c].cat.categories) for c in CAT_COLS},
        "training": {"rows": len(df), "projects": int(df.project_id.nunique()),
                     "milestones": int(df.milestone_key.nunique()),
                     "ftc_blocks": int(df[df.kind == GRADED_KIND].milestone_key.nunique())},
        "evaluation": json.loads(table.to_json(orient="records")),
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    cv.to_csv(out / "cv_predictions.csv.gz", index=False)
    print(f"\nbest: {best}  deployable (beats P6 and naive on unseen projects): {beats}")
    print(f"registered -> {out}")


if __name__ == "__main__":
    main()
