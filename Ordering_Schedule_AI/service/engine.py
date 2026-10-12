"""Prediction engine: rule baseline + ML prediction for UC1 and UC2.

The request is matched to the project in the Ordering Schedule snapshot
(data/interim) to fill what the request does not carry - construction
progress, AOP, contract category, OL. Request values always win: the
endpoints are what-if forms as much as lookups.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from features import (FEATURES, LABELS, RULE_LEAD_DAYS, TC_BUFFER_DAYS, UC2_FEATURES,  # noqa: E402
                      add_stacked, deadline, derive)
from rules import priority_class, rule_order, rule_tc  # noqa: E402

CLASSES = ["P1", "P2", "STANDARD"]
ORIGIN = {"China": "China", "SEA": "SEA", "ALMM": "Domestic", "ALCM": "Domestic", "DCR": "Domestic"}
SNAP_DATES = ["lta", "scod", "aop", "p6_data_date", "ftc_date", "deadline_date", "p6_final_ftc"]


def _d(x) -> date | None:
    if x is None or (isinstance(x, float) and np.isnan(x)) or x is pd.NaT:
        return None
    if isinstance(x, pd.Timestamp):
        return None if pd.isna(x) else x.date()
    if isinstance(x, date):
        return x
    s = str(x).strip()
    return date.fromisoformat(s[:10]) if s else None


def _num(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else float(x)


def _roman(s: str) -> int | None:
    vals = {"I": 1, "V": 5, "X": 10}
    s = s.upper()
    if not s or any(c not in vals for c in s):
        return None
    total = 0
    for i, c in enumerate(s):
        v = vals[c]
        total += -v if i + 1 < len(s) and vals[s[i + 1]] > v else v
    return total


def phase_number(label: str | None) -> int | None:
    """'PH-1', 'Ph-I', 'Phase II', 'Ph-II-A' -> 1, 1, 2, 2."""
    if not label:
        return None
    m = re.search(r"ph(?:ase)?[\s\-]*([0-9]+|[ivx]+)", str(label), re.I)
    if not m:
        return None
    tok = m.group(1)
    return int(tok) if tok.isdigit() else _roman(tok)


class Engine:
    def __init__(self):
        mdir = ROOT / "models"
        self.meta = json.loads((mdir / "metadata.json").read_text())
        self.site = joblib.load(mdir / "uc1_site_shift.joblib")
        self.lead50 = joblib.load(mdir / "uc1_lead_p50.joblib")
        self.lead90 = joblib.load(mdir / "uc1_lead_p90.joblib")
        self.prio = joblib.load(mdir / "uc2_priority.joblib")
        lt = self.meta["uc1_lead_time"]
        self.lead_off = {"p50": lt["p50"]["offset"], "p90": lt["p90"]["offset"]}
        self.lead_features = lt["features"]
        self.projects = pd.read_csv(ROOT / "data/interim/projects.csv",
                                    parse_dates=[c for c in SNAP_DATES if c not in ("ftc_date", "deadline_date")]
                                    + ["deadline_date"])
        self.phases = pd.read_csv(ROOT / "data/interim/phase_frame.csv", parse_dates=SNAP_DATES[:-1])
        self.median_ol = float(self.projects["ol"].median())
        m = self.meta["uc1_site_shift"]["metrics"]
        # Share of the rule engine's error the site model removes in grouped CV.
        self.site_skill = max(0.0, 1 - m["cv_mae_days"] / m["cv_mae_rule_days"])

    # ── snapshot matching ────────────────────────────────────────────────
    def match(self, project_id: str, project_name: str | None, capacity_mwp: float | None, phase: str | None):
        pid = re.sub(r"\s+", "", (project_id or "")).upper()
        p6 = self.projects["p6_name"].fillna("").str.replace(r"\s+", "", regex=True).str.upper()
        cand = self.projects[(p6 == pid) | p6.str.startswith(pid + "_")] if pid else self.projects.iloc[0:0]
        if cand.empty and project_name:
            cand = self.projects[self.projects["project"].str.strip().str.lower() == project_name.strip().lower()]
        if cand.empty:
            return None, None
        if len(cand) > 1:
            score = pd.Series(0.0, index=cand.index)
            if project_name:
                score += (cand["project"].str.strip().str.lower() == project_name.strip().lower()) * 1000
            score += (~cand["all_phases_charged"].astype(bool)) * 100
            if capacity_mwp:
                # The request may carry the phase or the whole project, so
                # take the closer of the two per candidate.
                ph = self.phases[self.phases["row_id"].isin(cand["row_id"])]
                ph_mwp = (ph["phase_mwac"] * ph["ol"]).groupby(ph["row_id"]).apply(list)
                def closeness(r):
                    opts = [r["capacity_mwp"]] + list(ph_mwp.get(r["row_id"], []))
                    opts = [o for o in opts if o == o and o is not None]
                    return -min((abs(o - capacity_mwp) for o in opts), default=1e6)
                score += cand.apply(closeness, axis=1)
            cand = cand.loc[[score.idxmax()]]
        proj = cand.iloc[0]
        ph = self.phases[self.phases["row_id"] == proj["row_id"]]
        n = phase_number(phase)
        prow = None
        norm = lambda s: re.sub(r"[\s\-_]", "", str(s)).upper()  # noqa: E731
        exact = ph[ph["phase"].map(norm) == norm(phase)] if phase else ph.iloc[0:0]
        if len(exact):  # 'Ph-II-B' must not land on 'Ph-II-A' (both phase 2)
            prow = exact.iloc[0]
        elif n is not None and not ph.empty:
            hit = ph[ph["phase"].map(phase_number) == n]
            prow = hit.iloc[0] if len(hit) else None
        if prow is None and len(ph) == 1:
            prow = ph.iloc[0]
        return proj, prow

    # ── features ─────────────────────────────────────────────────────────
    def base_row(self, req: dict, proj, prow, contract: str | None):
        notes = []
        ol = _num(req.get("ol")) or (_num(proj["ol"]) if proj is not None else None)
        if ol is None:
            ol = self.median_ol
            notes.append(f"OL unknown - portfolio median {ol:g} used to convert MWp to MWac")
        cap_mwac = _num(req.get("capacity_mwac")) or ((_num(req.get("capacity_mwp")) or 0) / ol or None)
        vendor = req.get("vendor_type") or (proj["vendor_type"] if proj is not None else None)
        ctype = (contract or (proj["contract_type"] if proj is not None else None) or "UNKNOWN").upper()
        g = (lambda c: proj[c] if proj is not None and c in proj else np.nan)
        er_share = g("erection_share")
        row = {
            "ftc_date": req["ftc_date"], "lta": req.get("lta_date"), "scod": req.get("scod_date"),
            "aop": g("aop"), "contract_type": ctype, "vendor_type": vendor, "mms_type": g("mms_type"),
            "capacity_mwac": cap_mwac,
            "balance_mwac": (_num(req.get("balance_ordering")) or 0) / ol,
            "inventory_mwac": (_num(req.get("inventory")) or 0) / ol,
            "receipt_mwac": (_num(req.get("receipt")) or 0) / ol,
            "transit_mwac": (_num(req.get("under_transit")) or 0) / ol,
            "erection_mwac": er_share * cap_mwac if cap_mwac and er_share == er_share else np.nan,
            "p6_data_date": g("p6_data_date"),
            "n_phases": prow["n_phases"] if prow is not None else g("n_phases_pending"),
            "phase_idx": prow["phase_idx"] if prow is not None else 0,
            "sap_mapped": True,
        }
        for k in ("piles", "structure", "modules"):
            row[f"{k}_pct"] = g(f"{k}_pct")
            row[f"{k}_planned_pct"] = g(f"{k}_planned_pct")
        row["behind_plan_pts"] = g("behind_plan_pts")
        if proj is None:
            notes.append("project not found in the Ordering Schedule snapshot - construction progress, AOP and "
                         "category unknown; prediction leans on the request fields only")
        return pd.DataFrame([row]), notes

    def _features(self, base: pd.DataFrame, today: date) -> pd.DataFrame:
        return derive(base, today)

    # ── UC1 pieces ───────────────────────────────────────────────────────
    def site_shift(self, X: pd.DataFrame) -> tuple[float, list]:
        pred = float(max(0.0, self.site.predict(X)[0]))
        contrib = self.site.predict(X, pred_contrib=True)[0][:-1]
        top = sorted(zip(FEATURES, contrib, X.iloc[0].values), key=lambda t: -abs(t[1]))[:4]
        return pred, [(f, float(c), v) for f, c, v in top if abs(c) >= 1]

    def lead_times(self, vendor: str | None, order_mwp: float, notes: list | None = None
                   ) -> tuple[float | None, float | None]:
        origin = ORIGIN.get(vendor or "")
        if origin is None:
            return None, None
        cap = self.meta["uc1_lead_time"].get("max_order_mwp", {}).get(origin)
        if cap and order_mwp > cap:
            if notes is not None:
                notes.append(f"Order of {order_mwp:g} MWp exceeds the largest {origin} order in the Ariba history "
                             f"({cap:g} MWp); lead time is read at that size")
            order_mwp = cap
        def row(share):
            r = {f"origin_{o}": float(origin == o) for o in ("China", "SEA", "Domestic")}
            r.update(order_size_mwp=order_mwp, delivered_share_before=share)
            return pd.DataFrame([r])[self.lead_features]
        p50 = float(self.lead50.predict(row(0.5))[0]) + self.lead_off["p50"]
        p90 = float(self.lead90.predict(row(0.9))[0]) + self.lead_off["p90"]
        return max(1.0, p50), max(p50, p90)

    # ── UC2 pieces ───────────────────────────────────────────────────────
    def stacked(self, X: pd.DataFrame, site_shift: float) -> pd.DataFrame:
        return add_stacked(X, [site_shift])

    def priority(self, X: pd.DataFrame) -> tuple[str, dict, list]:
        """X: stacked features (UC2_FEATURES)."""
        proba = np.asarray(self.prio.predict_proba(X))[0]
        cls = CLASSES[int(proba.argmax())]
        probs = {c: round(float(p), 3) for c, p in zip(CLASSES, proba)}
        drivers = []
        if self.meta["uc2_priority"]["kind"] == "catboost":
            from catboost import Pool
            sv = self.prio.get_feature_importance(Pool(X), type="ShapValues")  # (n, classes, feats+1)
            k = CLASSES.index(cls)
            contrib = sv[0][k][:-1]
            drivers = [(f, float(c), v) for f, c, v in sorted(zip(UC2_FEATURES, contrib, X.iloc[0].values),
                                                             key=lambda t: -t[1]) if c > 0.05][:5]
        return cls, probs, drivers

    @staticmethod
    def criticality(probs: dict) -> float:
        return round(100 * (probs["P1"] + 0.5 * probs["P2"]), 1)

    # ── shared deterministic parts ───────────────────────────────────────
    @staticmethod
    def deadline_of(base: pd.DataFrame) -> tuple[date | None, str]:
        dl, src = deadline(base["contract_type"], pd.to_datetime(base["scod"]), pd.to_datetime(base["aop"]))
        return _d(dl.iloc[0]), src.iloc[0]

    @staticmethod
    def transmission_shift(ftc: date, lta: date | None, dl: date | None) -> int:
        """Planner rule: LTA after the deadline -> the phase can wait for it."""
        if lta and dl and lta > dl and lta > ftc:
            return (lta - ftc).days
        return 0

    @staticmethod
    def supply_shortfall(ftc: date, vendor: str | None, balance: float, today: date) -> int:
        """Days FTC slips if the remaining balance is ordered no earlier than today."""
        ro = rule_order(ftc, vendor) if vendor else None
        if not balance or balance <= 0 or ro is None:
            return 0
        earliest = max(ro, today) + timedelta(days=RULE_LEAD_DAYS[vendor] + TC_BUFFER_DAYS)
        return max(0, (earliest - ftc).days)


def phrase(feature: str, value) -> str:
    """One readable driver line from a feature and its value."""
    v = None if value is None or (isinstance(value, float) and np.isnan(value)) else value
    if v is None:
        return f"{LABELS.get(feature, feature)} unknown"
    if feature == "deadline_gap_vs_phase_ftc":
        return (f"P6 FTC is {int(-v)} days after the deadline" if v < 0
                else f"Deadline approaching - {int(v)} days of margin after P6 FTC")
    if feature == "category_rank":
        return {2: "PPA commitment (penalty if late)", 1: "Merchant project (medium priority)",
                0: "Group / captive project (lowest priority)"}.get(int(v), "Contract category")
    if feature == "balance_share":
        return f"High balance still to order ({v:.0%} of capacity)" if v >= 0.5 else f"{v:.0%} of capacity still to order"
    if feature == "inventory_share":
        return "Inventory shortage at site" if v < 0.1 else f"Inventory covers {v:.0%} of capacity"
    if feature == "transit_share":
        return "Nothing in transit" if v == 0 else f"{v:.0%} of capacity in transit"
    if feature == "lta_after_deadline_days":
        if v > 0:
            return f"LTA lands {int(v)} days after the deadline - transmission binds"
        return "Transmission (LTA) ready by the deadline" if v == 0 else \
            f"Transmission (LTA) ready {int(-v)} days before the deadline"
    if feature == "transmission_binding_flag":
        return "LTA after the deadline - transmission binds" if v >= 1 else "Transmission is not the constraint"
    if feature == "realistic_slack_pred":
        return (f"Realistic FTC predicted {int(-v)} days after the deadline" if v < 0
                else f"Realistic FTC predicted {int(v)} days inside the deadline")
    if feature == "site_shift_pred":
        return f"Site readiness predicted to delay FTC {int(v)} days" if v >= 1 else "Site ready for the P6 FTC"
    if feature == "supply_shortfall_est":
        return (f"Ordering window passed - FTC slips {int(v)} days on supply alone" if v > 0
                else "Still time to order within the lead time")
    if feature == "rule_priority_rank":
        return f"Rule-engine priority on P6 dates: {['STANDARD', 'P2', 'P1'][int(v)]}"
    if feature == "ftc_risk_flag":
        return "High FTC risk - P6 FTC already after the deadline" if v >= 1 else "P6 FTC inside the deadline"
    if feature == "days_to_phase_ftc":
        return f"FTC in {int(v)} days" if v >= 0 else f"P6 FTC passed {int(-v)} days ago"
    if feature.endswith("_behind_pts") or feature == "behind_plan_pts":
        return f"{LABELS[feature].capitalize()} by {v:.0f} points" if v > 0 else f"{LABELS[feature].capitalize()}: on plan"
    if feature.endswith("_pct"):
        return f"{LABELS[feature].capitalize()} {v:.0%}" if v <= 1 else f"{LABELS[feature].capitalize()} {v:.0f}%"
    if feature == "scod_gap_vs_phase_ftc":
        return (f"SCOD milestone approaching ({int(v)} days after FTC)" if 0 <= v < 90
                else (f"SCOD already {int(-v)} days before FTC" if v < 0 else f"SCOD {int(v)} days after FTC"))
    if feature == "lta_gap_vs_phase_ftc":
        return f"LTA {int(v)} days after FTC" if v > 0 else f"LTA {int(-v)} days before FTC"
    return f"{LABELS.get(feature, feature).capitalize()}: {v:g}"
