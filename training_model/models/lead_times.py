"""
Step 4 - module lead times, by origin (import / domestic).

    training_model\\.venv\\Scripts\\python.exe training_model\\models\\lead_times.py

Statistics, not a trained model: only 20 module POs have dated receipts
(Ariba), 15 import and 5 domestic - too few to fit anything honestly. These
are the planner's lead-time assumptions, each published with its sample size.

Three clocks, because they answer different questions:
  po_to_first_receipt   PO date -> first module GR on site. Mixes
                        manufacturing + shipping + deliberate call-off.
  transit               Ariba dispatch -> GR. Pure logistics.
  delivery_span         first -> last GR of one PO: how long a PO trickles in.
A PO whose first receipt came > CALL_OFF_DAYS after the PO is an early bulk
order called off later, not a slow vendor; it is reported, not averaged in.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import RAW, REGISTRY  # noqa: E402

CALL_OFF_DAYS = 180


def q(s, p):
    s = s.dropna()
    return None if s.empty else int(round(float(np.quantile(s, p))))


def summary(s):
    s = s.dropna()
    return {"n": int(len(s)), "p50": q(s, 0.5), "p80": q(s, 0.8), "min": q(s, 0), "max": q(s, 1)}


def main():
    po = pd.read_csv(RAW / "module_po_lines.csv.gz", parse_dates=["document_date", "po_first_release"])
    rec = pd.read_csv(RAW / "module_receipts.csv.gz", parse_dates=["receipt_date", "dispatch_date"])
    po["po"], rec["po"] = po.po.astype(str), rec.po.astype(str)
    o = po.groupby("po").agg(origin=("origin", "first"), vendor=("vendor_name", "first"),
                             ordered_mw=("ordered_mw", "sum"),
                             po_date=("document_date", "min"), released=("po_first_release", "min")).reset_index()
    o["po_date"] = o.po_date.fillna(o.released)
    r = rec[rec.receipt_date.notna()]
    per_po = r.groupby("po").agg(first_gr=("receipt_date", "min"), last_gr=("receipt_date", "max"),
                                 received_mwp=("mwp", "sum")).reset_index()
    m = o.merge(per_po, on="po")
    m["po_to_first_receipt"] = (m.first_gr - m.po_date).dt.days
    m["delivery_span"] = (m.last_gr - m.first_gr).dt.days
    m["called_off"] = m.po_to_first_receipt > CALL_OFF_DAYS
    tr = r.merge(o[["po", "origin"]], on="po")
    tr["transit"] = (tr.receipt_date - tr.dispatch_date).dt.days
    tr = tr[tr.transit >= 0]          # a GR before its own dispatch is a data-entry error

    out = {"generated_at": datetime.now().isoformat(timespec="seconds"),
           "call_off_threshold_days": CALL_OFF_DAYS, "by_origin": {}}
    for origin in ("import", "domestic"):
        g = m[m.origin == origin]
        normal = g[~g.called_off]
        out["by_origin"][origin] = {
            "pos_with_receipts": int(len(g)),
            "po_to_first_receipt": summary(normal.po_to_first_receipt),
            "transit": summary(tr[tr.origin == origin].transit),
            "delivery_span": summary(normal.delivery_span),
            "called_off_pos": g[g.called_off][["po", "vendor", "ordered_mw", "po_to_first_receipt"]]
            .round(1).to_dict("records"),
        }
    out["coverage"] = {"module_pos": int(o.po.nunique()), "pos_with_dated_receipts": int(len(m)),
                       "note": "Receipt dates exist only for POs in the Ariba extract; SAP "
                               "goods-receipt documents carry no PO number."}
    dest = REGISTRY / "lead_time"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "lead_times.json").write_text(json.dumps(out, indent=2, default=str))
    m.to_csv(dest / "po_lead_times.csv", index=False)
    print(json.dumps(out["by_origin"], indent=2, default=str))


if __name__ == "__main__":
    main()
