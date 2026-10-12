"""Build the per-use-case training and test datasets from data/raw.

    python build_datasets.py            # from Ordering_Schedule_AI/src

Writes
    data/interim/        tidy tables parsed from the raw sheets (no labels)
    data/processed/ucN_*/ train.csv, test.csv, schema.json per dataset
    data/processed/DATASET_REPORT.md   the numbers behind every choice below

Label honesty. The raw data is one planning snapshot (as of 9 Oct 2026). It
carries no actual FTC, no actual delay and no planner-assigned priority, so
the only *measured* outcome in it is the Ariba dispatch/receipt history. Every
other label here is a proxy, and schema.json records which:

    measured   observed in a source system (Ariba IBD / GRN dates)
    inferred   an extrapolation the sheet itself computes (site-pace FTC)
    rule       the planning engine's own verdict (Remarks)
    weak       a documented heuristic over the above (priority)

Leakage. A feature that the proxy label was computed from is excluded from
that dataset's feature list — e.g. P6 pace/day is how the site-pace FTC is
computed, so it is not a UC3/UC4 feature. Splits are grouped by P6 project
(UC2-UC4) or by purchase order (UC1), so no project/PO sits on both sides.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold, GroupShuffleSplit

import parsers as P
from rules import P1_SLACK_DAYS, priority_class

ROOT = Path(__file__).resolve().parents[1]
RAW, INTERIM, PROCESSED = ROOT / "data/raw", ROOT / "data/interim", ROOT / "data/processed"
SEED, TEST_SIZE, N_FOLDS = 42, 0.25, 5
DUPLICATES: list[str] = []  # data-quality notes collected in main(), printed in the report

# Planning Rules sheet: "China and SEA 136 days; ALMM, ALCM and DCR 98 days".
# Confirmed against the sheet's own TC - Module Date gaps.
RULE_LEAD_DAYS = {"China": 136, "SEA": 136, "ALMM": 98, "ALCM": 98, "DCR": 98}
TC_BUFFER_DAYS = 45
CATEGORY_RANK = {"PPA": 2, "MERCHANT": 1, "GROUP": 0}


def days(a: pd.Series, b) -> pd.Series:
    """Whole days b - a (b may be a Series or a scalar Timestamp)."""
    return (b - a).dt.days if isinstance(b, pd.Series) else (b - a).dt.days


def contract_type(p6_name: str, category: str) -> tuple[str, bool]:
    """PPA / MERCHANT / GROUP from the P6 name token, as the planner does.

    Planning Rules: the display Category disagrees with the P6 token on 14
    rows, so the token wins; the display value is the fallback, flagged.
    """
    m = re.search(r"_(PPA|MERCHANT|GROUP)(?:_|$)", p6_name.upper().replace(" ", ""))
    if m:
        return m.group(1), True
    c = (category or "").strip().upper()
    return (c if c in ("PPA", "MERCHANT", "GROUP") else "UNKNOWN"), False


# ── Shared project features ──────────────────────────────────────────────────

def project_table(md: pd.DataFrame, sp: pd.DataFrame, plan: pd.DataFrame, as_of) -> pd.DataFrame:
    assert len(md) == len(sp) and (md["project"].values == sp["sp_project"].values).all(), \
        "Site Productivity blocks no longer line up with Module Deliveries rows"
    df = md.merge(sp.drop(columns="sp_project"), left_on="row_id", right_on="sp_block")
    ct = [contract_type(p, c) for p, c in zip(df["p6_name"], df["category"])]
    df["contract_type"] = [c for c, _ in ct]
    df["contract_from_p6_token"] = [t for _, t in ct]
    df["vendor_type"] = df["vendor_type"].replace("", "Unknown")
    df["rule_lead_days"] = df["vendor_type"].map(RULE_LEAD_DAYS)
    df["p6_final_ftc_days"] = days(pd.Series(as_of, index=df.index), df["p6_final_ftc"])
    for c in ("lta", "scod", "aop"):
        df[f"{c}_days_from_asof"] = days(pd.Series(as_of, index=df.index), df[c])
        df[f"{c}_gap_vs_final_ftc"] = days(df["p6_final_ftc"], df[c])  # >0: deadline after FTC
    # Capacity is measured in MWac (decided 2026-10-10): it is filled on every
    # project, MWp only where an OL is known. SAP reports module quantities in
    # MWp (DC), so they are converted with the project's OL. Every project
    # without an OL also has no SAP quantity, so the conversion loses nothing.
    for q in ("ordered", "balance", "receipt", "erection", "inventory", "transit"):
        df[f"{q}_mwac"] = df[f"{q}_mwp"] / df["ol"]
    df["structure_ready_no_modules_mwac"] = df["structure_ready_no_modules_mwdc"] / df["ol"]
    df["ordered_share"] = df["ordered_mwac"] / df["capacity_mwac"]
    df["receipt_share"] = df["receipt_mwac"] / df["capacity_mwac"]
    df["erection_share"] = df["erection_mwac"] / df["capacity_mwac"]
    df["inventory_share"] = df["inventory_mwac"] / df["capacity_mwac"]
    df["balance_share"] = df["balance_mwac"] / df["capacity_mwac"]
    # Category priority (business, 10 Oct): PPA highest (penalty), Merchant
    # medium (open-market sale), Group lowest (captive consumption).
    df["category_rank"] = df["contract_type"].map(CATEGORY_RANK)
    # Delivery progress against what is on order (the 'GRN at 50-60% triggers
    # the next order' scenario).
    df["grn_pct_of_ordered"] = df["receipt_mwp"] / df["ordered_mwp"]

    # Completion deadline the priority and LD logic measure against
    # (Planning Rules 'LTA breach check'; KT call 9 Oct): SCOD for a PPA
    # project, AOP (the sheet's ECOD) otherwise. A PPA project with no SCOD
    # falls back to AOP, flagged.
    ppa = df["contract_type"] == "PPA"
    df["deadline_date"] = np.where(ppa & df["scod"].notna(), df["scod"], df["aop"])
    df["deadline_date"] = pd.to_datetime(df["deadline_date"])
    df["deadline_source"] = np.select([ppa & df["scod"].notna(), df["aop"].notna()], ["SCOD", "AOP"], "none")
    df["deadline_days_from_asof"] = days(pd.Series(as_of, index=df.index), df["deadline_date"])
    df["deadline_gap_vs_final_ftc"] = days(df["p6_final_ftc"], df["deadline_date"])
    # 'If the LTA is after SCOD / ECOD the modules can be delayed': the
    # transmission line, not supply, sets when the plant can export.
    df["transmission_binding"] = (df["lta"] > df["deadline_date"]).where(df["lta"].notna() & df["deadline_date"].notna())
    df["lta_after_deadline_days"] = days(df["deadline_date"], df["lta"])
    df["data_age_days"] = days(df["p6_data_date"], pd.Series(as_of, index=df.index))
    for k in ("piles", "structure", "modules"):
        df[f"{k}_behind_pts"] = df[f"{k}_planned_pct"] - df[f"{k}_pct"]
    if not plan.empty:
        agg = plan.groupby("row_id").agg(rule_plan_mwp=("plan_mwp", "sum"),
                                         rule_plan_first_month=("month", "min"))
        df = df.merge(agg, left_on="row_id", right_index=True, how="left")
        df["rule_plan_first_month_days"] = days(pd.Series(as_of, index=df.index), df["rule_plan_first_month"])
    df["n_phases_pending"] = df["ftc_cell"].fillna("").map(
        lambda s: 0 if "No pending" in s or not s.strip() else len([l for l in s.split("\n") if l.strip()]))
    return df


PROJECT_NUM = [
    "capacity_mwac", "ol", "ordered_mwac", "balance_mwac", "receipt_mwac", "erection_mwac",
    "inventory_mwac", "transit_mwac", "ordered_share", "receipt_share", "erection_share", "inventory_share",
    "balance_share", "grn_pct_of_ordered", "rule_lead_days", "category_rank",
    "lta_days_from_asof", "scod_days_from_asof", "aop_days_from_asof", "deadline_days_from_asof",
    "lta_gap_vs_final_ftc", "scod_gap_vs_final_ftc", "aop_gap_vs_final_ftc", "deadline_gap_vs_final_ftc",
    "lta_after_deadline_days", "p6_final_ftc_days",
    "piles_pct", "structure_pct", "modules_pct", "piles_planned_pct", "structure_planned_pct",
    "modules_planned_pct", "piles_behind_pts", "structure_behind_pts", "modules_behind_pts",
    "behind_plan_pts", "data_age_days", "n_phases_pending",
]
PROJECT_CAT = ["contract_type", "vendor_type", "mms_type", "epc_group", "connectivity_phase",
               "transmission_binding", "deadline_source"]

# Site productivity: P6 pace (done / days since start), what pace the FTC
# needs, manpower at the site norms, and the supply-vs-site verdict built on
# them. These are the business's core FTC drivers ('Productivity Impact').
# But the only FTC label available today - the sheet's site-pace forecast -
# IS this arithmetic, so with that label they leak the answer. They are a
# separate, opt-in feature group (schema 'features.productivity'), off by
# default until actual FTC dates from P6 replace the proxy label.
PACE_COLS = [c for k in ("piles", "structure", "modules")
             for c in (f"{k}_pace_per_day", f"{k}_needed_per_day", f"{k}_manpower_needed")] + \
            ["structure_ready_no_modules_mwac"]
PACE_AUDIT = ["modules_finish_at_pace", "supply_vs_site"]


# ── Splitting ────────────────────────────────────────────────────────────────

def split(df: pd.DataFrame, group: str, stratify: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Grouped train/test split, then GroupKFold folds on train for CV.

    With a stratify column, a few seeds are tried and the one whose test-set
    class mix is closest to the full set is kept (a grouped split cannot
    stratify exactly when groups are this few).
    """
    best, best_err = None, np.inf
    for seed in range(SEED, SEED + (50 if stratify else 1)):
        gss = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=seed)
        tr, te = next(gss.split(df, groups=df[group]))
        if not stratify:
            best = (tr, te)
            break
        full = df[stratify].value_counts(normalize=True)
        test = df.iloc[te][stratify].value_counts(normalize=True).reindex(full.index, fill_value=0)
        err = float((full - test).abs().sum())
        if err < best_err:
            best, best_err = (tr, te), err
    train, test = df.iloc[best[0]].copy(), df.iloc[best[1]].copy()
    n = min(N_FOLDS, train[group].nunique())
    train["cv_fold"] = -1
    for f, (_, idx) in enumerate(GroupKFold(n_splits=n).split(train, groups=train[group])):
        train.iloc[idx, train.columns.get_loc("cv_fold")] = f
    return train, test


def write(name: str, train: pd.DataFrame, test: pd.DataFrame | None, schema: dict, extra: dict | None = None):
    out = PROCESSED / name
    out.mkdir(parents=True, exist_ok=True)
    stem = schema.pop("_stem", "")
    keep = [c for c in schema["id_columns"] + schema["features"]["numeric"] + schema["features"]["categorical"]
            + schema["features"].get("productivity", []) + schema["labels"] + schema.get("audit_columns", []) + ["cv_fold"] if c in train.columns]
    keep = list(dict.fromkeys(keep))
    train[keep].to_csv(out / f"{stem}train.csv", index=False)
    schema["rows"] = {"train": len(train), "train_groups": int(train[schema["group"]].nunique())}
    if test is not None:
        test[[c for c in keep if c != "cv_fold"]].to_csv(out / f"{stem}test.csv", index=False)
        schema["rows"].update(test=len(test), test_groups=int(test[schema["group"]].nunique()))
    schema.update(extra or {})
    (out / f"{stem}schema.json").write_text(json.dumps(schema, indent=2, default=str))
    return schema


# ── UC1 · Module ordering & TC delivery ──────────────────────────────────────

def uc1(lots: pd.DataFrame, raw_ledger: pd.DataFrame, phase_frame: pd.DataFrame, as_of):
    reports = {}

    # (a) Supply lead time per delivery lot — measured from Ariba.
    lt = lots.copy()
    lt["origin"] = [P.vendor_origin(v, p) for v, p in zip(lt["vendor"], lt["po"])]
    lt["po_to_dispatch_days"] = days(lt["po_date"], lt["dispatch_date"])
    lt["transit_days"] = days(lt["dispatch_date"], lt["grn_date"])
    lt["po_to_grn_days"] = days(lt["po_date"], lt["grn_date"])
    lt["excluded_reason"] = None
    lt.loc[lt["grn_date"].isna(), "excluded_reason"] = "awaiting GRN (no receipt date)"
    lt.loc[lt["transit_days"] < 0, "excluded_reason"] = "GRN before dispatch (data error)"
    excluded = lt[lt["excluded_reason"].notna()]
    lt = lt[lt["excluded_reason"].isna()].copy()

    lt = lt.sort_values(["po", "dispatch_date", "grn_date"])
    g = lt.groupby("po")
    lt["lot_seq"] = g.cumcount() + 1
    lt["days_since_first_dispatch"] = days(g["dispatch_date"].transform("min"), lt["dispatch_date"])
    lt["mwp_shipped_before"] = g["mwp"].cumsum() - lt["mwp"]
    po_size = lt.groupby("po")["mwp"].sum().rename("po_delivered_mwp")
    lt = lt.join(po_size, on="po")
    # Share of the order already delivered before this lot. Lets a model
    # answer "when will 50% / 90% of an order of size X be at site".
    lt["delivered_share_before"] = lt["mwp_shipped_before"] / lt["po_delivered_mwp"]
    lt["po_month"] = lt["po_date"].dt.month
    lt["po_year"] = lt["po_date"].dt.year
    lt["dispatch_month"] = lt["dispatch_date"].dt.month
    lt["multi_project_lot"] = lt["n_share_rows"] > 1
    # A PO placed long before goods move is a framework order: its PO date is a
    # contract date, not when the modules were called off.
    lt["po_to_first_dispatch_days"] = days(lt["po_date"], g["dispatch_date"].transform("min"))
    lt["framework_po"] = lt["po_to_first_dispatch_days"] > 180

    schema = {
        "_stem": "lead_time_",
        "use_case": "UC1 - supply lead time (feeds order date and TC forecast)",
        "grain": "one Ariba delivery lot (shares of a lot split across projects are merged)",
        "group": "po",
        "id_columns": ["po", "po_lines", "vendor", "plant", "projects", "po_date", "dispatch_date", "grn_date"],
        "features": {
            "numeric": ["qty", "mwp", "lot_seq", "days_since_first_dispatch", "mwp_shipped_before",
                        "delivered_share_before", "po_delivered_mwp", "po_month", "po_year", "dispatch_month"],
            "categorical": ["origin", "vendor", "framework_po", "multi_project_lot"],
        },
        "labels": ["po_to_grn_days", "po_to_dispatch_days", "transit_days"],
        "primary_label": "po_to_grn_days",
        "label_source": "measured - Ariba ZIBDSESREP inbound delivery (IBD) and GRN dates",
        "notes": [
            "Recommended order date = required-at-site date - predicted lead time (use the P90).",
            "po_to_first_dispatch_days / framework_po use the whole PO's history; at prediction time a PO "
            "has not shipped yet, so drop them (and lot_seq / days_since_first_dispatch) for a "
            "first-lot forecast, or keep them for a 'remaining lots' forecast.",
            "PO date is the SAP document date; for framework POs it precedes call-off by ~a year.",
            "POs 'Not in Ariba extract' are NOT treated as undelivered: delivered projects (e.g. AGEL Hybrid "
            "Merchant, 394 MWp received per SAP) also appear there, so absence means extract coverage, not "
            "an open order.",
        ],
        "excluded_rows": excluded["excluded_reason"].value_counts().to_dict(),
        "audit_columns": ["po_to_first_dispatch_days", "n_share_rows", "status"],
    }
    tr, te = split(lt, "po", stratify="origin")
    reports["lead_time"] = write("uc1_order_tc", tr, te, schema)
    reports["lead_time_frame"] = lt

    # (b) Monthly receipts per project series — measured, split in time.
    led = raw_ledger[raw_ledger["Status"] == "Received"].copy()
    led["grn_date"] = led["Received (GRN)"].map(P.to_date)
    led["mwp"] = led["MWp"].map(P.to_num)
    led["series"] = led["Project"] + " · " + led["Ariba plant"]
    led["month"] = led["grn_date"].dt.to_period("M").dt.to_timestamp()
    m = led.groupby(["series", "month"], as_index=False)["mwp"].sum().rename(columns={"mwp": "received_mwp"})
    full = []
    for s, grp in m.groupby("series"):
        idx = pd.date_range(grp["month"].min(), grp["month"].max(), freq="MS")
        grp = (grp.set_index("month")["received_mwp"].reindex(idx, fill_value=0.0)
               .rename_axis("month").reset_index())
        grp["series"] = s
        full.append(grp)
    m = pd.concat(full, ignore_index=True).sort_values(["series", "month"])
    g = m.groupby("series")["received_mwp"]
    m["lag1_mwp"] = g.shift(1)
    m["lag2_mwp"] = g.shift(2)
    m["cum_before_mwp"] = g.cumsum() - m["received_mwp"]
    m["month_idx"] = m.groupby("series").cumcount()
    m["calendar_month"] = m["month"].dt.month
    m["project"] = m["series"].str.split(" · ").str[0]
    cutoff = pd.Timestamp("2026-01-01")
    schema = {
        "_stem": "monthly_receipts_",
        "use_case": "UC1 - monthly module receipt forecasting",
        "grain": "one (project, Ariba plant) series per calendar month, zero-filled between first and last receipt",
        "group": "series",
        "id_columns": ["series", "project", "month"],
        "features": {"numeric": ["lag1_mwp", "lag2_mwp", "cum_before_mwp", "month_idx", "calendar_month"],
                     "categorical": ["project"]},
        "labels": ["received_mwp"],
        "primary_label": "received_mwp",
        "label_source": "measured - Ariba GRN dates; MWp per project as apportioned by WBS capacity share",
        "split": f"time-based: train month < {cutoff.date()}, test month >= {cutoff.date()}",
        "notes": ["Rows on shared plants are capacity-share apportionments, not separate measurements.",
                  "Only projects present in the Ariba extract have a series; the extract has no GRN after Aug-26."],
    }
    tr, te = m[m["month"] < cutoff].copy(), m[m["month"] >= cutoff].copy()
    tr["cv_fold"] = -1  # time series: use expanding-window CV, not random folds
    reports["monthly"] = write("uc1_order_tc", tr, te, schema)

    # (c) Phase order plan. No measured order date exists per phase, so the
    # target composes the three ordering scenarios the planners use (KT call,
    # 9 Oct): order for the phase's FTC; defer when transmission (LTA) lands
    # after the completion deadline; defer when the site cannot use modules
    # before its structures are ready (site-pace FTC). TC = that date - 45 d,
    # order = TC - lead time.
    ph = phase_frame.copy()
    origin_map = {"China": "China", "SEA": "SEA", "ALMM": "Domestic", "ALCM": "Domestic", "DCR": "Domestic"}
    measured = (lt[~lt["framework_po"]].groupby("origin")["po_to_grn_days"].quantile(0.9).round())
    ph["measured_lead_p90_days"] = ph["vendor_type"].map(origin_map).map(measured)

    eff = ph["ftc_date"].copy()
    lta_defer = ph["transmission_binding"].eq(True) & (ph["lta"] > eff)
    eff = eff.where(~lta_defer, ph["lta"])
    site_ftc = ph["ftc_date"] + pd.to_timedelta(ph["site_ftc_delay_days"].clip(lower=0).fillna(0), unit="D")
    site_defer = site_ftc > eff
    eff = eff.where(~site_defer, site_ftc)
    ph["label_effective_ftc"] = eff
    # One number carries both dates: order and TC are fixed offsets from the
    # effective FTC, so the shift vs P6 FTC is what a model has to learn.
    ph["label_ftc_shift_days"] = days(ph["ftc_date"], eff)
    ph["label_driver"] = np.select([site_defer, lta_defer], ["site pace", "transmission (LTA after deadline)"], "P6 FTC")
    need = ph["needs_ordering"].eq(True)
    a = pd.Series(as_of, index=ph.index)
    tc = eff - pd.Timedelta(days=TC_BUFFER_DAYS)
    order = tc - pd.to_timedelta(ph["rule_lead_days"], unit="D")
    order_meas = tc - pd.to_timedelta(ph["measured_lead_p90_days"], unit="D")
    ph["label_tc_date_days"] = days(a, tc)
    ph["label_order_date_days"] = days(a, order).where(need)
    ph["label_order_date_days_measured_lead"] = days(a, order_meas).where(need)
    ph["label_order_overdue"] = (order < as_of).where(need & order.notna())
    ph["label_order_shift_vs_rule_days"] = days(ph["rule_module_date"], order).where(need)
    ph["label_order_qty_mwac"] = ph["order_qty_mwac"].where(need)

    # The first SAP PO is comparable with a phase's rule order date only on a
    # single-phase project: on multi-phase projects it belongs to a phase that
    # has already charged (MLP T1, MLP AP New, NHPC BOO: -400 to -630 days).
    single = ph["n_phases"] == 1
    ph["actual_first_po_lag_days"] = np.where(single, days(ph["rule_module_date"], ph["po_placed"]), np.nan)
    labelled = ph[ph["label_tc_date_days"].notna()].copy()
    schema = {
        "_stem": "order_plan_",
        "use_case": "UC1 - module order date, order quantity and TC date per phase",
        "grain": "one pending FTC phase of a P6 project",
        "group": "p6_name",
        "id_columns": ["row_id", "project", "p6_name", "phase", "ftc_date", "tc_date", "rule_module_date",
                       "po_placed", "label_effective_ftc"],
        "features": {"numeric": PHASE_NUM + PROJECT_NUM, "categorical": PROJECT_CAT,
                     "productivity": PACE_COLS},
        "labels": ["label_ftc_shift_days", "label_order_date_days", "label_tc_date_days", "label_order_overdue",
                   "label_order_shift_vs_rule_days", "label_order_qty_mwac", "label_order_date_days_measured_lead",
                   "label_driver"],
        "primary_label": "label_ftc_shift_days (effective FTC - P6 phase FTC, all phases); order date and TC "
                         "follow as fixed offsets. label_order_date_days / label_tc_date_days are the same "
                         "target in absolute form.",
        "audit_columns": ["actual_first_po_lag_days", "measured_lead_p90_days", "needs_ordering",
                          "site_ftc_delay_days"] + PACE_AUDIT,
        "label_source": "rule (business scenarios) - effective FTC = latest of P6 phase FTC, LTA when it falls after "
                        "the deadline, and the site-pace FTC; TC = effective FTC - 45 d; order = TC - rule lead time "
                        "(China/SEA 136 d, ALMM/ALCM/DCR 98 d). Not an observed order date.",
        "notes": [
            "Order labels exist only for phases that still need ordering: phases are funded from the balance, "
            "earliest order date first, as the Planning Rules sequence them (needs_ordering). TC labels exist "
            "for every phase.",
            "label_order_date_days_measured_lead swaps the rule lead time for the measured Ariba P90 of "
            f"non-framework POs ({measured.to_dict()} days). Domestic PO dates are close to call-off, so that "
            "variant understates domestic lead time; it is a comparison, not the primary target.",
            "The site-pace part of the label is inferred from P6 pace: keep features.productivity off, or the "
            "model reads it back. The LTA / deadline part uses inputs that are legitimately features.",
            f"actual_first_po_lag_days (first SAP PO - rule module date) exists for "
            f"{int(ph['actual_first_po_lag_days'].notna().sum())} phases: a validation check, too few to train on.",
        ],
        "driver_counts": labelled["label_driver"].value_counts().to_dict(),
    }
    tr, te = split(labelled, "p6_name")
    reports["order_plan"] = write("uc1_order_tc", tr, te, schema)
    reports["order_frame"] = ph
    reports["excluded_lots"] = excluded
    return reports


PHASE_NUM = ["phase_mwac", "days_to_phase_ftc", "days_to_rule_module_date", "lta_gap_vs_phase_ftc",
             "scod_gap_vs_phase_ftc", "aop_gap_vs_phase_ftc", "deadline_gap_vs_phase_ftc",
             "phase_idx", "n_phases", "order_qty_mwac", "ftc_risk_flag"]


def build_phase_frame(phases: pd.DataFrame, projects: pd.DataFrame, as_of) -> pd.DataFrame:
    """Phase rows with project features, ordering need and supply feasibility.

    Ordering need follows the Planning Rules: phases sorted by their order
    date are each given their full requirement (phase MWac) from the balance
    until it runs out; later phases are not ordered.

    Supply shortfall is recomputed from the dates rather than read from the
    Remarks, which still carry the planner's old logic (KT call, 9 Oct): a
    phase still to order can be ordered no earlier than today, so its earliest
    FTC is max(rule order date, as_of) + lead time + 45 d.
    """
    ph = phases.merge(projects, on="row_id", how="left")
    a = pd.Series(as_of, index=ph.index)
    ph["days_to_phase_ftc"] = days(a, ph["ftc_date"])
    ph["days_to_rule_module_date"] = days(a, ph["rule_module_date"])
    for c in ("lta", "scod", "aop", "deadline_date"):
        ph[f"{c.replace('_date', '')}_gap_vs_phase_ftc"] = days(ph["ftc_date"], ph[c])
    # 'FTC risk' as the planner sees it from P6 alone: the planned FTC is
    # already after the deadline. Upstream of the realistic-FTC labels, so a
    # legitimate input (the API's ftc_risk_flag maps onto it).
    ph["ftc_risk_flag"] = (ph["deadline_gap_vs_phase_ftc"] < 0).astype(float).where(
        ph["deadline_gap_vs_phase_ftc"].notna())

    ph = ph.sort_values(["row_id", "rule_module_date", "phase_idx"])
    prior = ph.groupby("row_id")["phase_mwac"].cumsum() - ph["phase_mwac"]
    bal = ph["balance_mwac"].fillna(0)
    ph["order_qty_mwac"] = np.minimum((bal - prior).clip(lower=0), ph["phase_mwac"])
    ph["needs_ordering"] = (ph["order_qty_mwac"] > 0).where(ph["phase_mwac"].notna() & ph["ol"].notna())

    lead = pd.to_timedelta(ph["rule_lead_days"], unit="D")
    earliest_order = ph["rule_module_date"].where(ph["rule_module_date"] > as_of, as_of)
    earliest_ftc = earliest_order + lead + pd.Timedelta(days=TC_BUFFER_DAYS)
    short = days(ph["ftc_date"], earliest_ftc).clip(lower=0)
    ph["supply_shortfall_days"] = np.where(ph["needs_ordering"].eq(True), short,
                                           np.where(ph["needs_ordering"].eq(False), 0.0, np.nan))
    ph["supply_shortfall_days"] = ph["supply_shortfall_days"].where(
        ~(ph["needs_ordering"].eq(True) & lead.isna()))
    site = ph["site_ftc_delay_days"].clip(lower=0)
    ph["realistic_delay_days"] = pd.concat([ph["supply_shortfall_days"], site], axis=1).max(axis=1)
    ph["realistic_phase_ftc"] = ph["ftc_date"] + pd.to_timedelta(ph["realistic_delay_days"].fillna(0), unit="D")
    ph["slack_vs_deadline_days"] = days(ph["realistic_phase_ftc"], ph["deadline_date"])
    return ph.sort_index()


# ── UC2 · Priority (weak label) ──────────────────────────────────────────────

# P1_SLACK_DAYS lives in rules.py with the class logic; recorded in
# uc2_priority/schema.json.


def priority_label(r) -> tuple[str, str]:
    """P1 / P2 / STANDARD from LTA, SCOD/AOP, FTC and the PPA penalty.

    The business rule (10 Oct): priority is decided by LTA, SCOD and the FTC
    date, and PPA projects carry a penalty, so they must charge before their
    completion date. Planning Rules: PPA first, then P1, P2, standard. KT call:
    when the LTA falls after SCOD / ECOD, the project's modules can wait.

        P1        PPA, transmission not binding, realistic FTC within
                  P1_SLACK_DAYS of SCOD or past it (LD exposure)
        P2        any other PPA phase (PPA always outranks non-PPA), or a
                  Merchant phase whose realistic FTC is past its AOP and whose
                  transmission is not binding (Group is captive: lowest)
        STANDARD  everything else

    'Realistic FTC' = P6 phase FTC + max(supply shortfall, site-pace delay):
    the date the phase can actually charge, not the date P6 still shows.
    The sheet records no priority (STANDARD on all 49 projects), so this is a
    weak label until planners record P1/P2.
    """
    ppa = r["contract_type"] == "PPA"
    deferred = pd.notna(r["transmission_binding"]) and bool(r["transmission_binding"])
    slack = r["slack_vs_deadline_days"]
    has_slack = pd.notna(slack)
    why = []
    if has_slack:
        why.append(f"{'%d d after' % -slack if slack < 0 else '%d d before' % slack} {r['deadline_source']}")
    else:
        why.append("no SCOD/AOP")
    if pd.notna(r["realistic_delay_days"]) and r["realistic_delay_days"] > 0:
        why.append(f"realistic FTC +{int(r['realistic_delay_days'])} d vs P6")
    if deferred:
        why.append(f"LTA {int(r['lta_after_deadline_days'])} d after {r['deadline_source']} (can wait)")
    # The class itself comes from the shared rule (rules.priority_class), fed
    # the realistic FTC: Merchant can rise to P2, Group stays STANDARD.
    cls = priority_class(r["contract_type"], slack, r["lta_after_deadline_days"])
    return cls, f"{r['contract_type']}; " + "; ".join(why)


# Columns the weak labels are built from. Never features for those labels.
LABEL_SIGNALS = ["supply_shortfall_days", "realistic_delay_days", "realistic_phase_ftc", "slack_vs_deadline_days",
                 "site_ftc_forecast", "site_ftc_delay_days", "site_too_slow",
                 "rule_shortfall_days", "rule_site_late_days", "rule_ftc_past_lta", "rule_quota_pushed",
                 "rule_capacity_delayed_past_lta", "rule_overdue_order"]


def uc2(ph: pd.DataFrame):
    df = ph.copy()
    lab = df.apply(priority_label, axis=1)
    df["label_priority"] = [l for l, _ in lab]
    df["label_reason"] = [r for _, r in lab]
    schema = {
        "use_case": "UC2 - priority prediction (P1 / P2 / STANDARD)",
        "grain": "one pending FTC phase",
        "group": "p6_name",
        "id_columns": ["row_id", "project", "p6_name", "phase", "ftc_date", "deadline_date", "lta", "priority"],
        "features": {"numeric": PHASE_NUM + PROJECT_NUM, "categorical": PROJECT_CAT,
                     "productivity": PACE_COLS},
        "labels": ["label_priority"],
        "primary_label": "label_priority",
        "audit_columns": ["label_reason"] + LABEL_SIGNALS + PACE_AUDIT,
        "label_source": "weak - business rule over LTA, SCOD/AOP, realistic FTC and contract type "
                        "(priority_label() in build_datasets.py)",
        "label_rule": {
            "P1": f"PPA, LTA not after SCOD, realistic FTC < {P1_SLACK_DAYS} d before SCOD (or past it)",
            "P2": "any other PPA phase; or MERCHANT with realistic FTC past AOP and LTA not after AOP",
            "category order": "PPA (penalty) > MERCHANT (open market) > GROUP (captive, always STANDARD)",
            "STANDARD": "everything else",
            "deadline": "SCOD for PPA, AOP (the sheet's ECOD) otherwise; PPA without SCOD falls back to AOP",
            "realistic FTC": "P6 phase FTC + max(supply shortfall recomputed from lead time, site-pace delay)",
        },
        "notes": [
            "The sheet's Priority column is STANDARD on all 49 projects: no recorded P1/P2 exists.",
            "LTA, SCOD, AOP and P6 FTC gaps are features: they are the decision inputs. The realistic-FTC part "
            "(supply shortfall, site-pace delay) is inferred and excluded, so the model has to estimate it from "
            "progress, ordering and delivery state - that is what it adds over the rule.",
            "features.productivity is off by default: site-pace delay is computed from it.",
            "Phases of one project share most inputs; the split is grouped by project.",
        ],
        "class_counts": df["label_priority"].value_counts().to_dict(),
    }
    tr, te = split(df, "p6_name", stratify="label_priority")
    return write("uc2_priority", tr, te, schema), df


# ── UC3 / UC4 · FTC date and slippage ───────────────────────────────────────

def ftc_frame(projects: pd.DataFrame, phase_frame: pd.DataFrame, as_of) -> pd.DataFrame:
    df = projects[~projects["all_phases_charged"]].copy()
    a = pd.Series(as_of, index=df.index)
    df["label_site_ftc_date"] = df["site_ftc_forecast"]
    df["label_days_to_ftc"] = days(a, df["site_ftc_forecast"])
    # Supply side: worst phase shortfall, recomputed from lead times (not the
    # Remarks, which carry old logic). Missing where no phase could be tested.
    short = phase_frame.groupby("row_id")["supply_shortfall_days"].max()
    df["label_supply_shortfall_days"] = df["row_id"].map(short)
    df["label_site_delay_days"] = df["site_ftc_delay_days"]
    comp = df[["label_supply_shortfall_days", "label_site_delay_days"]]
    df["label_delay_days"] = comp.max(axis=1, skipna=True)
    df.loc[comp.isna().all(axis=1), "label_delay_days"] = np.nan
    df["label_is_delayed"] = np.where(df["site_too_slow"], True,
                                      np.where(df["label_delay_days"].notna(), df["label_delay_days"] > 0, np.nan))
    def binding(r):
        if r["site_too_slow"]:
            return "site (too slow to forecast)"
        if pd.isna(r["label_delay_days"]):
            return None
        if r["label_delay_days"] <= 0:
            return "none"
        site = r["label_site_delay_days"] if pd.notna(r["label_site_delay_days"]) else -1
        supply = r["label_supply_shortfall_days"] if pd.notna(r["label_supply_shortfall_days"]) else -1
        return "site pace" if site >= supply else "supply"

    df["label_binding_constraint"] = df.apply(binding, axis=1)

    # LD risk: how far the expected FTC lands after the contractual deadline.
    expected = df["p6_final_ftc"] + pd.to_timedelta(df["label_delay_days"].clip(lower=0), unit="D")
    df["label_expected_ftc"] = expected
    df["label_days_after_deadline"] = days(df["deadline_date"], expected)
    df["label_ld_risk"] = ((df["label_days_after_deadline"] > 0) & (df["contract_type"] == "PPA")).where(
        df["label_days_after_deadline"].notna())
    return df


FTC_FEATURES = PROJECT_NUM


def uc3(df: pd.DataFrame):
    d = df[df["label_days_to_ftc"].notna()].copy()
    schema = {
        "use_case": "UC3 - realistic FTC date",
        "grain": "one P6 project with pending FTC phases",
        "group": "p6_name",
        "id_columns": ["row_id", "project", "p6_name", "p6_final_ftc", "p6_data_date", "label_site_ftc_date"],
        "features": {"numeric": FTC_FEATURES, "categorical": PROJECT_CAT, "productivity": PACE_COLS},
        "labels": ["label_days_to_ftc", "label_site_ftc_date"],
        "primary_label": "label_days_to_ftc",
        "audit_columns": ["site_ftc_basis", "site_ftc_delay_days"] + PACE_AUDIT,
        "label_source": "inferred - 'FTC forecast (site speed)': P6 pace since start extrapolated to the "
                        "remaining scope. Not an actual FTC.",
        "notes": [
            "Predict days from the data date to FTC; predicted FTC = as_of + prediction.",
            "features.productivity (piles / structure / modules per day, needed per day, manpower) are the "
            "business's FTC drivers, but this label is computed from them: off by default, switch on once the "
            "label is actual FTC.",
            "Planned vs actual progress (*_planned_pct, *_pct, *_behind_pts) and P6 data age stay in: they are "
            "state, not the pace arithmetic.",
            "Real actual FTC dates live in P6 (p6_activity.actual_finish_date on charged FTC milestones). "
            "They are the label this dataset should move to; see DATASET_REPORT.md.",
            f"{int(df['site_too_slow'].sum())} projects are 'Too slow to forecast' (label censored, excluded here, "
            "kept as delayed in UC4).",
        ],
    }
    tr, te = split(d, "p6_name")
    return write("uc3_ftc_date", tr, te, schema), d


def uc4(df: pd.DataFrame):
    d = df[df["label_is_delayed"].notna()].copy()
    d["label_is_delayed"] = d["label_is_delayed"].astype(bool)
    schema = {
        "use_case": "UC4 - FTC slippage (probability and days)",
        "grain": "one P6 project with pending FTC phases",
        "group": "p6_name",
        "id_columns": ["row_id", "project", "p6_name", "p6_final_ftc"],
        "features": {"numeric": FTC_FEATURES, "categorical": PROJECT_CAT, "productivity": PACE_COLS},
        "labels": ["label_is_delayed", "label_delay_days", "label_site_delay_days",
                   "label_supply_shortfall_days", "label_binding_constraint",
                   "label_expected_ftc", "label_days_after_deadline", "label_ld_risk"],
        "primary_label": "label_is_delayed (classifier) / label_delay_days (regressor)",
        "audit_columns": LABEL_SIGNALS + PACE_AUDIT + ["deadline_date"],
        "label_source": "inferred + rule - delay = max(site-pace delay vs P6 FTC, supply shortfall recomputed "
                        "from lead time + 45 d TC). Not an observed delay.",
        "notes": [
            "Two different slip mechanisms: construction pace (site) and ordering too late for the lead time "
            "(supply). label_binding_constraint says which one sets the delay.",
            "LD risk (scenario 9): label_days_after_deadline = expected FTC - SCOD (PPA) or AOP; label_ld_risk "
            "is true only for PPA projects, which carry the penalty.",
            "'Too slow to forecast' projects are delayed with unknown days (label_delay_days missing): use them "
            "for the classifier, drop them for the regressor.",
            "Supply shortfall is recomputed per phase, not read from the Remarks (old logic, KT call 9 Oct); "
            "rule_shortfall_days is kept in the audit columns for comparison.",
            "features.productivity is off by default: site-pace delay is computed from it.",
        ],
        "class_counts": d["label_is_delayed"].value_counts().to_dict(),
        "ld_risk_counts": d["label_ld_risk"].value_counts(dropna=False).to_dict(),
    }
    tr, te = split(d, "p6_name", stratify="label_is_delayed")
    return write("uc4_slippage", tr, te, schema), d


# ── Report ───────────────────────────────────────────────────────────────────

def validate_monthly_plan(plan: pd.DataFrame, phases: pd.DataFrame, projects: pd.DataFrame) -> dict:
    """Which date the sheet's 'Month-wise Module Requirement at Site' cells sit
    on. A cell matches a month if one of its project's phases has its TC (or
    its order date) in that month. src/monthly.py rebuilds the plan on the
    answer."""
    ph = phases.copy()
    for c in ("tc_date", "rule_module_date"):
        ph[c] = pd.to_datetime(ph[c]).dt.to_period("M")
    cells = plan.assign(month=pd.to_datetime(plan["month"]).dt.to_period("M"))
    hit = lambda col: cells.apply(lambda r: bool((ph[(ph.row_id == r.row_id)][col] == r.month).any()), axis=1)  # noqa: E731
    grp = projects.groupby("epc_group").apply(lambda g: (g["capacity_mwac"] * g["ol"]).sum(), include_groups=False)
    return {"cells": len(cells), "projects": int(cells["row_id"].nunique()),
            "at_tc_month": int(hit("tc_date").sum()), "at_order_month": int(hit("rule_module_date").sum()),
            "epc_capacity_mwp": grp.round(2).dropna().to_dict()}


def report(as_of, md, projects, phases, lots, open_pos, r1, s2, d2, s3, d3, s4, d4, mv):
    lt = r1["lead_time_frame"]
    ph = r1["order_frame"]
    by_origin = lt.groupby("origin").agg(
        POs=("po", "nunique"), lots=("po", "size"), MWp=("mwp", "sum"),
        median_po_to_grn=("po_to_grn_days", "median"), p90_po_to_grn=("po_to_grn_days", lambda s: s.quantile(.9)),
        median_transit=("transit_days", "median")).round(1)
    by_origin["rule_lead_days"] = by_origin.index.map(lambda o: {"China": 136, "SEA": 136, "Domestic": 98}[o])
    nf = lt[~lt["framework_po"]].groupby("origin")["po_to_grn_days"].median().round(0)
    n = len(projects)
    fill = {c: f"{projects[c].notna().sum()}/{n}" for c in
            ["capacity_mwac", "capacity_mwp", "ol", "lta", "scod", "aop", "deadline_date", "ordered_mwac",
             "receipt_mwac", "erection_mwac", "inventory_mwac", "transit_mwac", "site_ftc_forecast", "po_placed"]}
    lag = ph.loc[ph["actual_first_po_lag_days"].notna(), ["project", "p6_name", "rule_module_date", "po_placed",
                                                         "actual_first_po_lag_days"]]
    # Recomputed supply shortfall against the planner's Remarks, per project.
    cmp_ = (ph.groupby(["row_id", "project", "p6_name"])
            .agg(recomputed_shortfall_d=("supply_shortfall_days", "max"),
                 remarks_shortfall_d=("rule_shortfall_days", "first"))
            .reset_index().drop(columns="row_id"))
    cmp_ = cmp_[cmp_[["recomputed_shortfall_d", "remarks_shortfall_d"]].fillna(0).sum(axis=1) > 0]
    pri = (d2.groupby(["contract_type", "label_priority"]).size().unstack(fill_value=0)
           .rename_axis(index="contract", columns=None))
    tb = projects[projects["transmission_binding"].eq(True) & ~projects["all_phases_charged"]][
        ["project", "p6_name", "lta", "deadline_source",
                                                              "deadline_date", "lta_after_deadline_days"]]

    disp = projects["category"].fillna("").str.upper()
    clash = projects[projects["contract_from_p6_token"] & disp.isin(["PPA", "MERCHANT", "GROUP"])
                     & (disp != projects["contract_type"]) & ~projects["all_phases_charged"]][
        ["project", "p6_name", "category", "contract_type"]].rename(
        columns={"category": "display_category", "contract_type": "used (P6 token)"})
    n_order = int(ph["label_order_date_days"].notna().sum())

    def tbl(df: pd.DataFrame, keep_index: bool = False) -> str:
        df = df.reset_index() if keep_index else df.reset_index(drop=True)
        cols = list(df.columns)
        lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
        for _, r in df.iterrows():
            lines.append("| " + " | ".join("" if pd.isna(v) else (v.strftime("%d-%b-%y") if isinstance(v, pd.Timestamp)
                                                                  else (f"{v:g}" if isinstance(v, float) else str(v)))
                                           for v in r) + " |")
        return "\n".join(lines)

    def rows(s):
        r = s["rows"]
        return f"{r['train']} train ({r['train_groups']} groups) / {r.get('test', '-')} test ({r.get('test_groups', '-')} groups)"

    md_text = f"""# Ordering Schedule AI — dataset report

Generated by `src/build_datasets.py` from `data/raw/*` (snapshot as of **{as_of:%d %b %Y}**).
Every number below is recomputed on each run.

## 1. What the raw data contains

| Sheet | Grain | Rows |
|---|---|---|
| Module Deliveries | P6 project | {n} projects ({int(projects['all_phases_charged'].sum())} fully charged), {len(phases)} pending FTC phases |
| Ariba Ledger | delivery lot (IBD → GRN) | {len(lots)} unique lots on {lots['po'].nunique()} POs; {len(open_pos)} POs not in the Ariba extract |
| Site Productivity | P6 project × activity | {len(md)} project blocks (1:1 with Module Deliveries, order-checked) |
| Planning Rules | rule text | used to verify lead times, the TC buffer and phase sequencing |

**There is no Phase Orders sheet in `data/raw`.** The KT call confirms it is the planner's month-wise *plan*
(rule output), not actual orders, so it would be a baseline, never a label. Phase FTC / TC / Module dates are
parsed from the multi-line cells of Module Deliveries.

Fill rate of the key project columns ({n} projects after de-duplication):

{tbl(pd.DataFrame([fill]).T.rename(columns={0: 'filled'}).rename_axis('column'), keep_index=True)}

**Capacity is measured in MWac.** MWac is filled on every project, MWp only where an OL is known. SAP module
quantities (ordered, receipt, erection, inventory, transit, balance) arrive in MWp and are converted with the
project's OL (`*_mwac`); every project without an OL also has no SAP quantity, so nothing is lost. Ariba lot
sizes stay in MWp: a lot carries no OL of its own.

Data-quality fixes applied: {'; '.join(DUPLICATES) or 'none'}.

## 2. Business logic from the KT calls (9 Oct) and how it is encoded

| What the planners said | Where it lands |
|---|---|
| TC = FTC − 45 d; module order = TC − lead time (China/SEA 136 d, ALMM/DCR 98 d) | `rule_lead_days`; UC1 labels; supply shortfall |
| AOP is the ECOD (final project completion) — there is no separate ECOD column | `deadline_date` = SCOD for PPA, AOP otherwise |
| If LTA falls after SCOD / ECOD, the project's modules can be delayed | `transmission_binding`, `lta_after_deadline_days`; UC1 effective FTC; UC2 priority |
| PPA carries a penalty if FTC misses its date; group and merchant do not | UC2: PPA always ≥ P2; UC4 `label_ld_risk` (PPA only) |
| Order only once structures are ready; excess modules with low progress → don't order | UC1 effective FTC follows the site-pace FTC when later; productivity group |
| Balance = capacity − ordered; inventory = receipt − erection | phase funding from `balance_mwac` (`needs_ordering`, `order_qty_mwac`) |
| The Remarks text still carries the old logic | supply shortfall **recomputed** from dates; Remarks kept for audit only (table below) |
| P6 is synced nightly but no history was kept | one snapshot only; history is the top data ask (section 7) |

Recomputed supply shortfall vs the Remarks (projects where either is non-zero):

{tbl(cmp_)}

**PPA vs non-PPA is read from the P6 name token** (Planning Rules; KT call: "P6 name is universal"). It now
decides priority and LD risk, so these pending projects — where the display category disagrees — need a
planner's confirmation:

{tbl(clash)}

The recomputed figure tests lead time only. Where the Remarks show more (typically 61 d), the planner also
pushed the order into a later month because the vendor's monthly quota was full — quota levelling is the
planner's allocation, not a property of the project, so it is not in the label.

Projects with pending phases whose transmission is the binding constraint (LTA after their deadline):

{tbl(tb)}

## 3. Labels the request asked for, and what exists

| Requested label | In the data? | What these datasets use instead |
|---|---|---|
| `actual_ftc` | **No** | UC3: site-pace FTC forecast (*inferred*) — {s3['rows']['train'] + s3['rows'].get('test', 0)} projects |
| `delay_days` | **No** | UC4: max(site-pace delay, recomputed supply shortfall) (*inferred + rule*) |
| `priority` | **No variance** — `STANDARD` on all {len(md)} projects | UC2: business rule over LTA, SCOD/AOP, realistic FTC and PPA (*weak*) |
| `actual_order_date` | Partly: first SAP PO date on {int(md['po_placed'].notna().sum())} projects | UC1: scenario-based order date (*rule*) + measured Ariba lead time; PO-vs-rule lag for validation ({len(lag)} phases) |

The only **measured** outcome in the raw data is the Ariba dispatch/receipt history, so UC1's lead-time
model is the one trained on ground truth. UC1's order plan and UC2–UC4 are trained on proxies until real
outcomes are joined in.

## 4. Findings that change the rule engine's assumptions

**Lead times are not 136 / 98 days.** Measured PO → GRN per lot:

{tbl(by_origin, keep_index=True)}

Excluding framework POs (PO date > 180 days before first dispatch), median PO → GRN is
{', '.join(f'{o} {int(v)} d' for o, v in nf.items())}. Domestic POs are raised when goods are nearly ready
(median PO → first dispatch {int(lt[lt.origin == 'Domestic'].po_to_dispatch_days.median())} d), so for domestic supply the
PO date is close to a call-off, not an order lead time. Three import POs (5310000688, 5310000698, 5310000890)
are framework orders placed ~a year before dispatch.

**Lead times in the sheet are confirmed against its own dates**: TC − Module Date is 136 d for China and SEA,
98 d for ALMM — matching the Planning Rules sheet and the KT call.

**First PO vs rule module date** (single-phase projects only — on a multi-phase project the first PO belongs
to a phase that has already charged):

{tbl(lag)}

Negative = the PO went out before the rule says it had to. The AGEL Merchant 50 MW PO (May-25) is on plant
51Z6, shared with the 150 MW sibling, so it predates this project's own order window.

**The sheet's Month-wise Module Requirement at Site is placed in the TC month.** Of {mv['cells']} planned
cells on {mv['projects']} projects, {mv['at_tc_month']} fall in the TC month of one of the project's phases and
{mv['at_order_month']} in an order month (where another phase's order month happens to coincide). Each cell is the phase requirement (phase MWac × OL), funded from the
balance in order-date sequence. Rows timed by **Site speed** (planner column) carry no monthly cells: their
requirement follows structure completion, which `src/monthly.py` rebuilds from the P6 structure pace.
UC1 returns both plans (`monthly_requirement.rule_engine` / `.ai`) and `GET /api/ai/v1/monthly-plan?epc=`
groups them by contractor.

A contractor header such as "Amara Raja (4 projects · 641.3 MWp)" is the **sum** of its projects' capacities
(MWac × OL), not one figure split among them: {', '.join(f'{k} {v:g}' for k, v in mv['epc_capacity_mwp'].items() if v)} MWp
(contractors whose projects carry no OL have no MWp).

## 5. The datasets

| Dataset | Grain | Label (source) | Rows | Split |
|---|---|---|---|---|
| `uc1_order_tc/lead_time_*` | delivery lot | `po_to_grn_days` (measured) | {rows(r1['lead_time'])} | grouped by PO, origin-balanced |
| `uc1_order_tc/monthly_receipts_*` | project-plant × month | `received_mwp` (measured) | {rows(r1['monthly'])} | time: < Jan-26 / ≥ Jan-26 |
| `uc1_order_tc/order_plan_*` | pending phase | `label_order_date_days`, `label_tc_date_days`, `label_order_qty_mwac` (rule) | {rows(r1['order_plan'])} | grouped by project |
| `uc2_priority/*` | pending phase | `label_priority` (weak) | {rows(s2)} | grouped by project, class-balanced |
| `uc3_ftc_date/*` | project | `label_days_to_ftc` (inferred) | {rows(s3)} | grouped by project |
| `uc4_slippage/*` | project | `label_is_delayed`, `label_delay_days`, `label_ld_risk` (inferred + rule) | {rows(s4)} | grouped by project, class-balanced |

UC1 order-date driver: {r1['order_plan']['driver_counts']}. Order-date labels exist for {n_order} of
{len(ph)} phases (those still funded from the balance); the rest are already ordered or have no OL/SAP data, and
carry a TC label only. MLP T1's site-pace forecast (+720 d) puts its effective FTC in 2029 — the sheet's own
extrapolation, but an outlier a regressor should be robust to.
UC4 delayed: {s4['class_counts']}; LD risk (PPA past SCOD): {s4['ld_risk_counts']}.

UC2 priority by contract type:

{tbl(pri, keep_index=True)}

Each folder has a `schema.json` listing feature columns (`numeric`, `categorical`, and an opt-in
`productivity` group), label columns, the group column, label provenance and exclusions. `train*.csv`
carries a `cv_fold` column (GroupKFold, {N_FOLDS} folds; `-1` for the time-series set) — with groups this few,
report cross-validated metrics, not the single test split.

Excluded Ariba lots: {r1['lead_time']['excluded_rows']}.

## 6. The 15 business scenarios against the data

| # | Scenario | Data available now | In the datasets |
|---|---|---|---|
| 1 | Progress delay | planned vs actual % (piles / structure / modules), P6 FTC, data date | yes — `*_pct`, `*_planned_pct`, `*_behind_pts`, `days_to_phase_ftc` |
| 2 | P6 not updated | P6 data date only; **no FTC revision history** | partial — `data_age_days` |
| 3 | Productivity | piles / structure / modules per day; **stringing not in P6** | opt-in `productivity` group (leaks with the current FTC label) |
| 4 | Procurement delay | PO date, dispatch, GRN per lot; **no manufacturing status** | yes — UC1 lead time; `grn_pct_of_ordered`, transit |
| 5 | Inventory-based ordering | inventory, ordered, balance, phase requirement | yes — `order_qty_mwac`, `inventory_share` |
| 6 | GRN trigger at 50–60 % | receipt vs ordered | yes — `grn_pct_of_ordered` |
| 7 | CEO approval | none | workflow, not an ML input |
| 8 | Order freeze & lock | none | workflow, not an ML input |
| 9 | LD risk | SCOD, predicted FTC | yes — UC4 `label_days_after_deadline`, `label_ld_risk` |
| 10 | Transmission readiness | LTA date; **no line progress in the raw sheets** | partial — `transmission_binding`, `lta_*` gaps |
| 11 | Vendor capacity | monthly ceilings in Planning Rules, rule plan in MWac | not modelled — quota levelling is the planner's optimisation, not a prediction |
| 12 | Weather | none | missing |
| 13 | Vendor payment risk | finance checklist count only; **no invoice / payment** | missing |
| 14 | Root cause | which constraint binds | UC1 `label_driver`, UC4 `label_binding_constraint`, UC2 `label_reason` |
| 15 | Impact analysis | the rule chain FTC → TC → order | encoded in the UC1 labels; a propagation step, not a model |

## 7. Limits — read before training

* **Sample size.** UC3/UC4 have one row per project: tens of rows. Any model here is a baseline; its test
  metric on a handful of projects is noise. Prefer simple, regularised models and CV.
* **Proxy labels.** UC1's order plan and UC2 encode the planners' rules; UC3/UC4 learn the sheet's own
  extrapolation. A model trained on them reproduces the rule from upstream signals — useful where those signals
  are incomplete, but the UI must present every output as inferred, never as measured.
* **Productivity leakage.** Pace per day is the business's main FTC driver and is exactly how the current FTC
  label is computed. It is an opt-in feature group, off by default, until actual FTC dates replace the label.
* **One snapshot.** Every relative-day feature is measured from {as_of:%d %b %Y}; there is no history of how
  P6 FTC dates moved, so slippage cannot be learned from past slippage yet.

## 8. What would turn the proxies into real labels

1. **Actual FTC** — P6 `p6_activity.actual_finish_date` on charged FTC milestones, against
   `baseline_finish_date`. This is in the Akasha database already; it gives UC3/UC4 a measured label for every
   commissioned phase ({int(projects['all_phases_charged'].sum())} projects here are fully charged but carry no FTC date in the sheet).
2. **Snapshots over time** — P6 is synced nightly (KT call); storing each night's FTC and progress per project
   gives FTC revision history (scenario 2) and a measured slippage label within weeks.
3. **Planner-assigned P1/P2** — `project_mapping.priority` exists and is empty.
4. **PO release / call-off date** — separates framework-PO contract dates from the real order date.
5. Weather, vendor payment status, manufacturing status, stringing progress, transmission line progress.
"""
    (PROCESSED / "DATASET_REPORT.md").write_text(md_text, encoding="utf-8")


def main():
    # processed/ is fully generated: clear it so a renamed dataset cannot leave
    # a stale file behind.
    shutil.rmtree(PROCESSED, ignore_errors=True)
    INTERIM.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    as_of = P.read_as_of(RAW)
    md, plan = P.parse_module_deliveries(RAW)
    phases = P.explode_phases(md)
    lots, open_pos = P.parse_ariba(RAW)
    raw_ledger = pd.read_csv(RAW / "Ariba Ledger.csv", dtype=str, encoding="utf-8-sig").fillna("")
    sp = P.parse_site_productivity(RAW)

    projects = project_table(md, sp, plan, as_of)
    # One P6 project listed twice (under two EPC groups) would put conflicting
    # labels in one group. Keep the row the master mapping knows (has capacity).
    ordered = projects.sort_values("capacity_mwp", na_position="first")
    dropped = ordered[ordered.duplicated("p6_name", keep="last")]
    projects = projects.drop(index=dropped.index)
    phases = phases[phases["row_id"].isin(projects["row_id"])]
    DUPLICATES.extend(f"{r.p6_name}: dropped row under '{r.epc_group}' ({r.project}); kept the mapped row"
                      for r in dropped.itertuples())
    for name, df in [("projects", projects), ("phases", phases), ("ariba_lots", lots),
                     ("ariba_pos_not_in_extract", open_pos), ("site_productivity", sp), ("rule_monthly_plan", plan)]:
        df.to_csv(INTERIM / f"{name}.csv", index=False)

    pf = build_phase_frame(phases, projects, as_of)
    pf.to_csv(INTERIM / "phase_frame.csv", index=False)
    r1 = uc1(lots, raw_ledger, pf, as_of)
    s2, d2 = uc2(pf)
    ff = ftc_frame(projects, pf, as_of)
    s3, d3 = uc3(ff)
    s4, d4 = uc4(ff)
    mv = validate_monthly_plan(plan, phases, projects)
    report(as_of, md, projects, phases, lots, open_pos, r1, s2, d2, s3, d3, s4, d4, mv)
    print(f"Monthly plan cells {mv['cells']} on {mv['projects']} projects | at TC month {mv['at_tc_month']} "
          f"| at order month {mv['at_order_month']}")

    for n, s in [("UC1 lead time", r1["lead_time"]), ("UC1 monthly", r1["monthly"]),
                 ("UC1 order plan", r1["order_plan"]), ("UC2 priority", s2), ("UC3 FTC", s3), ("UC4 slip", s4)]:
        print(f"{n:18} {s['rows']}")
    print("UC1 drivers", r1["order_plan"]["driver_counts"])
    print("UC2 classes", s2["class_counts"], "| UC4 classes", s4["class_counts"], "| LD", s4["ld_risk_counts"])


if __name__ == "__main__":
    main()
