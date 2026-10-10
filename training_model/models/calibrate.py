"""
Step 3b - make the forecast ranges honest.

    training_model\\.venv\\Scripts\\python.exe training_model\\models\\calibrate.py

The quantile models' own P20/P80 came out too narrow on unseen projects
(P20-P80 held ~25% of actual dates instead of ~60%; P80 ~51% instead of
~80%). So the range is set from the model's real errors instead: on the
cross-validation forecasts (projects the model never saw), take the 20th and
80th percentile of (actual - P50) per horizon bucket, and use those as the
offsets around P50. "4 in 5 blocks finished before P80" is then a measured
statement, not a hope. (Split-conformal calibration, per horizon.)

Writes the offsets into the latest model's meta.json; no retraining.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import REGISTRY  # noqa: E402
from models.train_ftc import bucket  # noqa: E402


def main():
    d = sorted((REGISTRY / "ftc_slip").glob("v*"))[-1]
    meta = json.loads((d / "meta.json").read_text())
    cv = pd.read_csv(d / "cv_predictions.csv.gz")
    p50 = f"{meta['algorithm']}_p50"
    cv["resid"] = cv.slip_days - cv[p50]
    cv["bucket"] = cv.days_to_baseline.map(bucket)

    def offsets(g):
        return {"p20": round(float(np.quantile(g.resid, 0.2)), 1),
                "p80": round(float(np.quantile(g.resid, 0.8)), 1), "n": int(len(g))}

    cal = {"all": offsets(cv)}
    for b, g in cv.groupby("bucket"):
        cal[b] = offsets(g)

    # Coverage check, leave-one-fold-out: offsets learned on the other folds,
    # tested on this one - so the reported coverage is not measured on the
    # same errors the offsets were fitted to.
    hits20 = hits80 = n = 0
    for f in cv.fold.unique():
        tr, te = cv[cv.fold != f], cv[cv.fold == f]
        for b, g in te.groupby("bucket"):
            ref = tr[tr.bucket == b] if (tr.bucket == b).sum() >= 30 else tr
            lo, hi = np.quantile(ref.resid, 0.2), np.quantile(ref.resid, 0.8)
            hits20 += int(((g.resid >= lo) & (g.resid <= hi)).sum())
            hits80 += int((g.resid <= hi).sum())
            n += len(g)
    meta["calibration"] = {
        "method": "split-conformal offsets around P50 from cross-validation errors, per horizon bucket",
        "offsets": cal,
        "check_leave_fold_out": {"band_p20_p80_coverage_pct": round(hits20 / n * 100, 1),
                                 "p80_coverage_pct": round(hits80 / n * 100, 1), "rows": n},
    }
    (d / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta["calibration"], indent=2))


if __name__ == "__main__":
    main()
