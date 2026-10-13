"""Train the UC1 and UC2 models, benchmark them against the rule engine, save.

    python train.py          # from Ordering_Schedule_AI/src, after build_datasets.py

Models
    UC1  site_shift  LightGBM regressor - days the site pushes FTC beyond P6
         lead_p50/90 LightGBM quantile   - PO -> receipt days (measured, Ariba)
    UC2  priority    CatBoost vs XGBoost - P1 / P2 / STANDARD, best by grouped CV

Every model is tuned with grouped CV on the train split (groups = P6 project
or PO), scored once on the held-out test split, compared with the rule
engine, then refit on all labelled rows for serving. Artifacts go to models/;
runs and registered models to MLflow (sqlite store in Ordering_Schedule_AI/).

The UC1 order date and TC are not separate models: they are fixed offsets
from the effective FTC (rule engine), so the model learns the one uncertain
part - how far site readiness pushes FTC - and the rule adds the rest.
"""
from __future__ import annotations

import itertools
import json
import os
import warnings
from datetime import datetime
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import accuracy_score, f1_score, log_loss, mean_absolute_error, confusion_matrix
from sklearn.model_selection import GroupKFold
from xgboost import XGBClassifier

import parsers as P
from features import FEATURES, UC2_FEATURES, add_stacked, derive
from rules import priority_class

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
INTERIM, PROCESSED, MODELS = ROOT / "data/interim", ROOT / "data/processed", ROOT / "models"
SEED = 42
CLASSES = ["P1", "P2", "STANDARD"]
DATE_COLS = ["ftc_date", "lta", "scod", "aop", "p6_data_date", "deadline_date"]


def load_phase_frame() -> pd.DataFrame:
    pf = pd.read_csv(INTERIM / "phase_frame.csv", parse_dates=[c for c in DATE_COLS])
    pf["sap_mapped"] = pf["ol"].notna()
    return pf


def split_of(name: str, stem: str = "") -> tuple[set, set]:
    tr = pd.read_csv(PROCESSED / name / f"{stem}train.csv")
    te = pd.read_csv(PROCESSED / name / f"{stem}test.csv")
    return set(tr["p6_name"]), set(te["p6_name"])


def folds_for(groups: pd.Series, n: int = 5) -> list[tuple[np.ndarray, np.ndarray]]:
    k = min(n, groups.nunique())
    return list(GroupKFold(n_splits=k).split(np.zeros(len(groups)), groups=groups))


def grid(space: dict) -> list[dict]:
    keys = list(space)
    return [dict(zip(keys, v)) for v in itertools.product(*space.values())]


# ── UC1 · site shift (LightGBM) ──────────────────────────────────────────────

def train_site_shift(pf: pd.DataFrame, as_of) -> dict:
    """Target: days the site-pace FTC lands after the P6 FTC (>= 0).

    'Too slow to forecast' projects are censored (no number) and left out.
    """
    y = pf["site_ftc_delay_days"].clip(lower=0)
    m = y.notna() & ~pf["site_too_slow"].astype(bool)
    d, y = pf[m].reset_index(drop=True), y[m].reset_index(drop=True)
    X = derive(d, as_of)
    tr_g, te_g = split_of("uc1_order_tc", "order_plan_")
    tr, te = d["p6_name"].isin(tr_g).values, d["p6_name"].isin(te_g).values

    # ~20 projects, one at +720 d: only heavily regularised trees beat the
    # median (looser settings scored worse than a constant in grouped CV).
    space = {"objective": ["l1"], "num_leaves": [2, 3], "min_child_samples": [6, 10, 15],
             "n_estimators": [50, 150], "learning_rate": [0.05], "reg_lambda": [0.0, 10.0]}
    cv = folds_for(d.loc[tr, "p6_name"].reset_index(drop=True))
    Xtr, ytr = X[tr].reset_index(drop=True), y[tr].reset_index(drop=True)
    best, best_mae, best_oof = None, np.inf, None
    for p in grid(space):
        oof = np.zeros(len(ytr))
        for a, b in cv:
            mdl = lgb.LGBMRegressor(**p, random_state=SEED, verbose=-1).fit(Xtr.iloc[a], ytr.iloc[a])
            oof[b] = np.clip(mdl.predict(Xtr.iloc[b]), 0, None)
        mae = mean_absolute_error(ytr, oof)
        if mae < best_mae:
            best, best_mae, best_oof = p, mae, oof
    mdl = lgb.LGBMRegressor(**best, random_state=SEED, verbose=-1).fit(Xtr, ytr)
    pred_te = np.clip(mdl.predict(X[te]), 0, None)
    final = lgb.LGBMRegressor(**best, random_state=SEED, verbose=-1).fit(X, y)
    resid = np.abs(ytr - best_oof)
    metrics = {
        "rows": int(len(y)), "train_rows": int(tr.sum()), "test_rows": int(te.sum()),
        "cv_mae_days": round(best_mae, 1),
        "cv_mae_rule_days": round(mean_absolute_error(ytr, np.zeros(len(ytr))), 1),
        "cv_mae_median_days": round(mean_absolute_error(ytr, np.full(len(ytr), np.median(ytr))), 1),
        "test_mae_median_days": round(mean_absolute_error(y[te], np.full(te.sum(), np.median(ytr))), 1),
        "test_mae_days": round(mean_absolute_error(y[te], pred_te), 1),
        "test_mae_rule_days": round(mean_absolute_error(y[te], np.zeros(te.sum())), 1),
        "residual_p50_days": round(float(np.quantile(resid, 0.5)), 1),
        "residual_p90_days": round(float(np.quantile(resid, 0.9)), 1),
    }
    return {"model": final, "params": best, "metrics": metrics, "features": FEATURES,
            "baseline": "rule engine: P6 FTC holds (shift 0)"}


def site_predictions(pf: pd.DataFrame, as_of, params: dict) -> np.ndarray:
    """Site-shift prediction for every phase, for stacking into UC2.

    Phases with a site-pace label get an out-of-fold prediction (their own
    project held out), so UC2 never sees a prediction fitted on its own row.
    Phases without one get the model fitted on all labelled rows.
    """
    X = derive(pf, as_of)
    y = pf["site_ftc_delay_days"].clip(lower=0)
    lab = (y.notna() & ~pf["site_too_slow"].astype(bool)).values
    pred = np.zeros(len(pf))
    full = lgb.LGBMRegressor(**params, random_state=SEED, verbose=-1).fit(X[lab], y[lab])
    pred[~lab] = full.predict(X[~lab])
    idx = np.where(lab)[0]
    for a, b in folds_for(pf["p6_name"].iloc[idx].reset_index(drop=True)):
        m = lgb.LGBMRegressor(**params, random_state=SEED, verbose=-1).fit(X.iloc[idx[a]], y.iloc[idx[a]])
        pred[idx[b]] = m.predict(X.iloc[idx[b]])
    return np.clip(pred, 0, None)


# ── UC1 · supply lead time (LightGBM quantile, measured) ─────────────────────

LEAD_FEATURES = ["origin_China", "origin_SEA", "origin_Domestic", "order_size_mwp", "delivered_share_before"]


def lead_matrix(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame({f"origin_{o}": (df["origin"] == o).astype(float) for o in ("China", "SEA", "Domestic")})
    X["order_size_mwp"] = df["po_delivered_mwp"].values
    X["delivered_share_before"] = df["delivered_share_before"].values
    return X[LEAD_FEATURES]


def train_lead_time() -> dict:
    """PO -> GRN days per lot, framework POs excluded (their PO date is a
    contract date, ~a year before call-off). Asked at share 0.5 / 0.9 of an
    order it answers 'when is half / 90% of an order of this size at site'."""
    tr = pd.read_csv(PROCESSED / "uc1_order_tc/lead_time_train.csv")
    te = pd.read_csv(PROCESSED / "uc1_order_tc/lead_time_test.csv")
    tr, te = tr[~tr["framework_po"]].reset_index(drop=True), te[~te["framework_po"]].reset_index(drop=True)
    rule = {"China": 136, "SEA": 136, "Domestic": 98}
    out = {"features": LEAD_FEATURES, "rows": {"train": len(tr), "test": len(te),
                                              "train_pos": int(tr["po"].nunique()), "test_pos": int(te["po"].nunique())}}
    cv = folds_for(tr["po"])
    space = {"num_leaves": [3, 7], "min_child_samples": [5, 15], "n_estimators": [100, 300],
             "learning_rate": [0.05]}
    for alpha in (0.5, 0.9):
        def pinball(y, q):
            e = y - q
            return float(np.mean(np.maximum(alpha * e, (alpha - 1) * e)))
        best, best_loss, best_oof = None, np.inf, None
        for p in grid(space):
            oof = np.zeros(len(tr))
            for a, b in cv:
                mdl = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **p, random_state=SEED, verbose=-1)
                mdl.fit(lead_matrix(tr.iloc[a]), tr["po_to_grn_days"].iloc[a])
                oof[b] = mdl.predict(lead_matrix(tr.iloc[b]))
            loss = pinball(tr["po_to_grn_days"].values, oof)
            if loss < best_loss:
                best, best_loss, best_oof = p, loss, oof
        # Conformal calibration: shift the quantile by the out-of-fold
        # residual quantile so the stated coverage holds on unseen POs
        # (uncalibrated, the P90 covered only ~73% of test lots).
        offset = float(np.quantile(tr["po_to_grn_days"].values - best_oof, alpha))
        mdl = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **best, random_state=SEED, verbose=-1)
        mdl.fit(lead_matrix(tr), tr["po_to_grn_days"])
        q_te = mdl.predict(lead_matrix(te)) + offset
        rule_te = te["origin"].map(rule).values
        allrows = pd.concat([tr, te], ignore_index=True)
        final = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **best, random_state=SEED, verbose=-1)
        final.fit(lead_matrix(allrows), allrows["po_to_grn_days"])
        key = f"p{int(alpha * 100)}"
        m = {"cv_pinball": round(best_loss, 2), "test_pinball": round(pinball(te["po_to_grn_days"].values, q_te), 2),
             "test_pinball_rule": round(pinball(te["po_to_grn_days"].values, rule_te), 2),
             "test_coverage": round(float(np.mean(te["po_to_grn_days"].values <= q_te)), 2)}
        if alpha == 0.5:
            m["test_mae_days"] = round(mean_absolute_error(te["po_to_grn_days"], q_te), 1)
            m["test_mae_rule_days"] = round(mean_absolute_error(te["po_to_grn_days"], rule_te), 1)
        m["calibration_offset_days"] = round(offset, 1)
        out[key] = {"model": final, "params": best, "metrics": m, "offset": offset}
    out["baseline"] = "rule engine lead time: China/SEA 136 d, ALMM/DCR (domestic) 98 d"
    # Largest order seen per origin. The API caps order size here: beyond it
    # a tree borrows another origin's behaviour (no domestic PO above ~83 MWp,
    # so a 200 MWp ALMM order was being priced like a Chinese import).
    allrows = pd.concat([tr, te], ignore_index=True)
    out["max_order_mwp"] = allrows.groupby("origin")["po_delivered_mwp"].max().round(1).to_dict()
    return out


# ── UC2 · priority (CatBoost vs XGBoost) ─────────────────────────────────────

def train_priority(pf: pd.DataFrame, as_of, site_pred: np.ndarray) -> dict:
    lab = pd.concat([pd.read_csv(PROCESSED / "uc2_priority/train.csv").assign(_split="train"),
                     pd.read_csv(PROCESSED / "uc2_priority/test.csv").assign(_split="test")])
    pf = pf.assign(_site_pred=site_pred)
    d = pf.merge(lab[["row_id", "phase", "label_priority", "_split"]], on=["row_id", "phase"])
    X = add_stacked(derive(d, as_of), d["_site_pred"].values)
    y = d["label_priority"].map({c: i for i, c in enumerate(CLASSES)}).values
    tr, te = (d["_split"] == "train").values, (d["_split"] == "test").values
    Xtr, ytr = X[tr].reset_index(drop=True), y[tr]
    cv = folds_for(d.loc[tr, "p6_name"].reset_index(drop=True))

    # Rule engine baseline: the same rule on the P6 FTC (what the planner sees today).
    rule = np.array([CLASSES.index(priority_class(c, s, l)) for c, s, l in
                     zip(d["contract_type"], X["deadline_gap_vs_phase_ftc"], X["lta_after_deadline_days"])])

    def make(kind, p):
        if kind == "catboost":
            return CatBoostClassifier(loss_function="MultiClass", auto_class_weights="Balanced", verbose=0,
                                      random_seed=SEED, allow_writing_files=False, **p)
        return XGBClassifier(objective="multi:softprob", num_class=3, eval_metric="mlogloss",
                             random_state=SEED, verbosity=0, **p)

    spaces = {"catboost": {"depth": [2, 4], "iterations": [200, 500], "learning_rate": [0.05], "l2_leaf_reg": [3, 10]},
              "xgboost": {"max_depth": [2, 3], "n_estimators": [100, 300], "learning_rate": [0.05],
                          "reg_lambda": [1.0, 10.0], "min_child_weight": [1, 3]}}
    results = {}
    for kind, space in spaces.items():
        best = None
        for p in grid(space):
            oof = np.zeros((len(ytr), 3))
            for a, b in cv:
                if len(set(ytr[a])) < 3:
                    continue
                oof[b] = make(kind, p).fit(Xtr.iloc[a], ytr[a]).predict_proba(Xtr.iloc[b])
            pred = oof.argmax(1)
            score = (f1_score(ytr, pred, average="macro"), -log_loss(ytr, np.clip(oof, 1e-6, 1), labels=[0, 1, 2]))
            if best is None or score > best[0]:
                best = (score, p, pred)
        results[kind] = {"params": best[1], "cv_macro_f1": round(best[0][0], 3),
                         "cv_logloss": round(-best[0][1], 3), "cv_accuracy": round(accuracy_score(ytr, best[2]), 3)}
    kind = max(results, key=lambda k: (results[k]["cv_macro_f1"], -results[k]["cv_logloss"]))
    p = results[kind]["params"]
    mdl = make(kind, p).fit(Xtr, ytr)
    pred_te = np.asarray(mdl.predict_proba(X[te])).argmax(1)
    final = make(kind, p).fit(X, y)
    metrics = {
        "chosen": kind, "candidates": results,
        "rows": int(len(y)), "train_rows": int(tr.sum()), "test_rows": int(te.sum()),
        "class_counts": {c: int((y == i).sum()) for i, c in enumerate(CLASSES)},
        "test_macro_f1": round(f1_score(y[te], pred_te, average="macro"), 3),
        "test_accuracy": round(accuracy_score(y[te], pred_te), 3),
        "test_confusion (rows=true P1,P2,STD)": confusion_matrix(y[te], pred_te, labels=[0, 1, 2]).tolist(),
        "test_macro_f1_rule": round(f1_score(y[te], rule[te], average="macro"), 3),
        "test_accuracy_rule": round(accuracy_score(y[te], rule[te]), 3),
        "cv_macro_f1_rule": round(f1_score(ytr, rule[tr], average="macro"), 3),
    }
    return {"model": final, "kind": kind, "params": p, "metrics": metrics, "features": UC2_FEATURES,
            "classes": CLASSES, "baseline": "rule engine on the P6 FTC (realistic delay ignored)"}


# ── MLflow ───────────────────────────────────────────────────────────────────

def log_mlflow(name: str, params: dict, metrics: dict, model, flavor: str):
    if os.getenv("MLFLOW_DISABLE") == "1":
        return None
    try:
        import mlflow
        mlflow.set_tracking_uri(f"sqlite:///{(ROOT / 'mlflow.db').as_posix()}")
        # Artifacts under Ordering_Schedule_AI/mlruns whatever the working
        # directory (the default './mlruns' followed wherever train.py ran).
        if mlflow.get_experiment_by_name("ordering-schedule-ai") is None:
            mlflow.create_experiment("ordering-schedule-ai", artifact_location=(ROOT / "mlruns").as_uri())
        mlflow.set_experiment("ordering-schedule-ai")
        flat = {k: v for k, v in metrics.items() if isinstance(v, (int, float))}
        with mlflow.start_run(run_name=name) as run:
            mlflow.log_params({k: str(v) for k, v in params.items()})
            mlflow.log_metrics(flat)
            getattr(mlflow, flavor).log_model(model, name="model", registered_model_name=name)
        return run.info.run_id
    except Exception as e:  # tracking must never block training
        print(f"  MLflow logging skipped for {name}: {e}")
        return None


def main():
    MODELS.mkdir(exist_ok=True)
    as_of = P.read_as_of(ROOT / "data/raw")
    pf = load_phase_frame()

    print("UC1 site shift (LightGBM) ...")
    s = train_site_shift(pf, as_of)
    print("UC1 lead time (LightGBM quantile) ...")
    lt = train_lead_time()
    print("UC2 priority (CatBoost vs XGBoost, stacked on UC1 site shift) ...")
    pr = train_priority(pf, as_of, site_predictions(pf, as_of, s["params"]))

    joblib.dump(s["model"], MODELS / "uc1_site_shift.joblib")
    joblib.dump(lt["p50"]["model"], MODELS / "uc1_lead_p50.joblib")
    joblib.dump(lt["p90"]["model"], MODELS / "uc1_lead_p90.joblib")
    joblib.dump(pr["model"], MODELS / "uc2_priority.joblib")

    runs = {
        "uc1_site_shift_lgbm": log_mlflow("uc1_site_shift_lgbm", s["params"], s["metrics"], s["model"], "lightgbm"),
        "uc1_lead_time_p50_lgbm": log_mlflow("uc1_lead_time_p50_lgbm", lt["p50"]["params"], lt["p50"]["metrics"],
                                             lt["p50"]["model"], "lightgbm"),
        "uc1_lead_time_p90_lgbm": log_mlflow("uc1_lead_time_p90_lgbm", lt["p90"]["params"], lt["p90"]["metrics"],
                                             lt["p90"]["model"], "lightgbm"),
        f"uc2_priority_{pr['kind']}": log_mlflow(f"uc2_priority_{pr['kind']}", pr["params"],
                                                 {k: v for k, v in pr["metrics"].items() if k != "candidates"},
                                                 pr["model"], "catboost" if pr["kind"] == "catboost" else "xgboost"),
    }
    meta = {
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "data_as_of": str(as_of.date()),
        "features": FEATURES,
        "uc1_site_shift": {k: s[k] for k in ("params", "metrics", "baseline")},
        "uc1_lead_time": {"features": LEAD_FEATURES, "rows": lt["rows"], "baseline": lt["baseline"],
                          "max_order_mwp": lt["max_order_mwp"],
                          "p50": {k: lt["p50"][k] for k in ("params", "metrics", "offset")},
                          "p90": {k: lt["p90"][k] for k in ("params", "metrics", "offset")}},
        "uc2_priority": {k: pr[k] for k in ("kind", "params", "metrics", "classes", "baseline", "features")},
        "mlflow_runs": runs,
        "label_provenance": {
            "uc1_site_shift": "inferred - sheet's site-pace FTC forecast vs P6 FTC",
            "uc1_lead_time": "measured - Ariba IBD / GRN dates",
            "uc2_priority": "weak - business rule on realistic FTC, LTA, SCOD/AOP, contract category",
        },
    }
    (MODELS / "metadata.json").write_text(json.dumps(meta, indent=2, default=str))
    print(json.dumps({"uc1_site_shift": s["metrics"],
                      "uc1_lead_p50": lt["p50"]["metrics"], "uc1_lead_p90": lt["p90"]["metrics"],
                      "uc2_priority": {k: v for k, v in pr["metrics"].items()}}, indent=1, default=str))


if __name__ == "__main__":
    main()
