"""Model features, computed the same way for training and for the API.

Training builds them from data/interim/phase_frame.csv; the API builds them
from the request, enriched with the matched project's snapshot row. Both go
through derive(), so a feature can never mean one thing in training and
another in production.

Quantities are scale-free shares of capacity. The API's two contracts send
capacity at different grains (order-tc-forecast: the phase, 203 MWp;
priority-predict: the project, 675 MWp), so an absolute MW feature would mean
different things per endpoint; a share does not.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TC_BUFFER_DAYS = 45
# Planning Rules sheet, confirmed by the sheet's own TC - Module Date gaps and
# by the existing service's rule_engine output (ALMM: TC - 98 d).
RULE_LEAD_DAYS = {"China": 136, "SEA": 136, "ALMM": 98, "ALCM": 98, "DCR": 98}
CATEGORY_RANK = {"PPA": 2, "MERCHANT": 1, "GROUP": 0}

FEATURES = [
    # dates (days; reference = today in the API, the snapshot date in training)
    "days_to_phase_ftc", "lta_gap_vs_phase_ftc", "scod_gap_vs_phase_ftc", "aop_gap_vs_phase_ftc",
    "deadline_gap_vs_phase_ftc", "lta_after_deadline_days", "ftc_risk_flag",
    # the planner's rule as a crisp flag: LTA strictly after the deadline. A
    # tree learning the threshold from the day count alone misplaces it
    # (LTA on the deadline day was read as deferred).
    "transmission_binding_flag",
    # contract and supply; the rule engine's own priority on the P6 dates
    # (2 = P1, 1 = P2, 0 = STANDARD) - the baseline the model corrects
    "category_rank", "rule_lead_days", "is_hsat", "rule_priority_rank",
    # days FTC slips if the balance is ordered today (deterministic from inputs)
    "supply_shortfall_est",
    # material position, as shares of capacity
    "balance_share", "inventory_share", "receipt_share", "transit_share", "erection_share",
    # construction state (P6), from the snapshot
    "piles_pct", "structure_pct", "modules_pct", "piles_behind_pts", "structure_behind_pts",
    "modules_behind_pts", "behind_plan_pts", "data_age_days",
    # phase position
    "n_phases", "phase_idx",
]

# Readable names for explanations.
LABELS = {
    "days_to_phase_ftc": "days to P6 FTC", "lta_gap_vs_phase_ftc": "LTA vs FTC (days)",
    "scod_gap_vs_phase_ftc": "SCOD vs FTC (days)", "aop_gap_vs_phase_ftc": "AOP vs FTC (days)",
    "deadline_gap_vs_phase_ftc": "deadline vs FTC (days)", "lta_after_deadline_days": "LTA after deadline (days)",
    "ftc_risk_flag": "P6 FTC already after deadline", "category_rank": "contract category",
    "transmission_binding_flag": "LTA after deadline",
    "rule_lead_days": "vendor lead time", "is_hsat": "tracker (HSAT) site",
    "rule_priority_rank": "rule-engine priority on P6 dates",
    "supply_shortfall_est": "supply shortfall if ordered today",
    "site_shift_pred": "predicted site-readiness delay", "realistic_slack_pred": "realistic deadline margin",
    "balance_share": "share still to order", "inventory_share": "inventory share",
    "receipt_share": "received share", "transit_share": "in-transit share", "erection_share": "erected share",
    "piles_pct": "piles done", "structure_pct": "structure done", "modules_pct": "modules mounted",
    "piles_behind_pts": "piles behind plan", "structure_behind_pts": "structure behind plan",
    "modules_behind_pts": "modules behind plan", "behind_plan_pts": "behind P6 baseline",
    "data_age_days": "P6 data age", "n_phases": "phases in project", "phase_idx": "phase position",
}


def deadline(contract: pd.Series, scod: pd.Series, aop: pd.Series) -> tuple[pd.Series, pd.Series]:
    """SCOD for PPA, AOP (the sheet's ECOD) otherwise; each falls back to the other."""
    ppa = contract.eq("PPA")
    d = np.where(ppa, scod.fillna(aop), aop.fillna(scod))
    src = np.where(ppa, np.where(scod.notna(), "SCOD", np.where(aop.notna(), "AOP", "none")),
                   np.where(aop.notna(), "AOP", np.where(scod.notna(), "SCOD", "none")))
    return pd.to_datetime(pd.Series(d, index=contract.index)), pd.Series(src, index=contract.index)


def _days(a: pd.Series, b: pd.Series) -> pd.Series:
    return (pd.to_datetime(b) - pd.to_datetime(a)).dt.days


def derive(base: pd.DataFrame, today) -> pd.DataFrame:
    """Feature matrix from base columns.

    base needs: ftc_date, lta, scod, aop, contract_type, vendor_type, mms_type,
    capacity_mwac, balance_mwac, inventory_mwac, receipt_mwac, transit_mwac,
    erection_mwac, piles_pct, structure_pct, modules_pct, the three
    *_planned_pct, behind_plan_pts, p6_data_date, n_phases, phase_idx;
    optional sap_mapped (True where SAP quantities are known).
    Missing values stay missing (the tree models handle NaN).
    """
    b = base.copy()
    for c in ("ftc_date", "lta", "scod", "aop", "p6_data_date"):
        b[c] = pd.to_datetime(b[c])
    ref = pd.Series(pd.Timestamp(today), index=b.index)
    dl, _ = deadline(b["contract_type"], b["scod"], b["aop"])
    f = pd.DataFrame(index=b.index)
    f["days_to_phase_ftc"] = _days(ref, b["ftc_date"])
    for c in ("lta", "scod", "aop"):
        f[f"{c}_gap_vs_phase_ftc"] = _days(b["ftc_date"], b[c])
    f["deadline_gap_vs_phase_ftc"] = _days(b["ftc_date"], dl)
    f["lta_after_deadline_days"] = _days(dl, b["lta"])
    f["ftc_risk_flag"] = (f["deadline_gap_vs_phase_ftc"] < 0).astype(float).where(f["deadline_gap_vs_phase_ftc"].notna())
    f["transmission_binding_flag"] = (f["lta_after_deadline_days"] > 0).astype(float).where(
        f["lta_after_deadline_days"].notna())
    f["category_rank"] = b["contract_type"].map(CATEGORY_RANK)
    f["rule_lead_days"] = b["vendor_type"].map(RULE_LEAD_DAYS)
    f["is_hsat"] = b["mms_type"].astype(str).str.upper().str.startswith("HSAT").astype(float).where(b["mms_type"].notna())
    from rules import priority_class  # rules imports this module's constants
    rank = {"P1": 2.0, "P2": 1.0, "STANDARD": 0.0}
    f["rule_priority_rank"] = [rank[priority_class(c, s, l)] for c, s, l in
                               zip(b["contract_type"], f["deadline_gap_vs_phase_ftc"], f["lta_after_deadline_days"])]
    cap = b["capacity_mwac"].where(b["capacity_mwac"] > 0)
    # On a project SAP knows (it has an OL), a blank quantity in the sheet is
    # zero: AE2L shows Ordered blank with Balance = Capacity; MSEDCL A01 shows
    # Balance blank because it is over-ordered. The API sends explicit zeros.
    # On an unmapped project a blank is unknown and stays missing.
    mapped = b["sap_mapped"].astype(bool) if "sap_mapped" in b else pd.Series(False, index=b.index)
    for q in ("balance", "inventory", "receipt", "transit", "erection"):
        qty = b[f"{q}_mwac"].where(~mapped, b[f"{q}_mwac"].fillna(0))
        f[f"{q}_share"] = qty / cap
    for k in ("piles", "structure", "modules"):
        f[f"{k}_pct"] = b[f"{k}_pct"]
        f[f"{k}_behind_pts"] = b[f"{k}_planned_pct"] - b[f"{k}_pct"]
    # Ordered no earlier than today, the balance reaches site at today + lead,
    # and charges 45 d later: the slip past the P6 FTC, where balance remains.
    short = (f["rule_lead_days"] + TC_BUFFER_DAYS - f["days_to_phase_ftc"]).clip(lower=0)
    f["supply_shortfall_est"] = short.where(f["balance_share"].fillna(0) > 0, 0.0).where(f["rule_lead_days"].notna())
    f["behind_plan_pts"] = b["behind_plan_pts"]
    f["data_age_days"] = _days(b["p6_data_date"], ref)
    f["n_phases"] = b["n_phases"]
    f["phase_idx"] = b["phase_idx"]
    return f[FEATURES].astype(float)


# UC2 stacks the UC1 site model on top: its predicted site delay (out-of-fold
# in training) and the realistic deadline margin it implies. The priority
# label is defined on the realistic FTC, so the classifier gets it explicitly
# instead of having to infer it from four projects.
UC2_FEATURES = FEATURES + ["site_shift_pred", "realistic_slack_pred"]


def add_stacked(X: pd.DataFrame, site_shift_pred) -> pd.DataFrame:
    X = X.copy()
    X["site_shift_pred"] = np.asarray(site_shift_pred, dtype=float)
    delay = np.fmax(X["site_shift_pred"].values, X["supply_shortfall_est"].fillna(0).values)
    X["realistic_slack_pred"] = X["deadline_gap_vs_phase_ftc"] - delay
    return X[UC2_FEATURES]
