"""Raw-sheet parsers for the Ordering Schedule AI datasets.

The four CSVs in data/raw are exports of the Ordering Schedule workbook, laid
out for people, not machines: two-row headers, EPC group rows between project
rows, phase dates packed into one multi-line cell, and planner commentary in
free text. Everything here turns them into tidy tables and does nothing else:
no feature engineering, no labels, no imputation. A value that is not in the
sheet stays missing.

Date cells are 'dd-Mon-yy'. The sheet header carries the data date
("As of 9 Oct 2026"), which every relative-day feature is measured from.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
import pandas as pd

DATE_RE = r"\d{2}-[A-Z][a-z]{2}-\d{2}"


def to_date(s) -> pd.Timestamp:
    if s is None:
        return pd.NaT
    m = re.search(DATE_RE, str(s))
    return pd.to_datetime(m.group(0), format="%d-%b-%y") if m else pd.NaT


def to_num(s) -> float:
    if s is None:
        return np.nan
    t = str(s).replace(",", "").replace("%", "").strip()
    if t in ("", "-"):
        return np.nan
    try:
        return float(t)
    except ValueError:
        return np.nan


def _read(path: Path) -> list[list[str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


# ── Module Deliveries ────────────────────────────────────────────────────────

def as_of_from_rows(rows: list[list[str]]) -> pd.Timestamp | None:
    """Data date from the sheet header, e.g. 'As of 9 Oct 2026, 4:25 pm'."""
    for row in rows[:3]:
        for cell in row:
            m = re.search(r"As of (\d{1,2} \w{3} \d{4})", cell)
            if m:
                return pd.to_datetime(m.group(1), format="%d %b %Y")
    return None


def read_as_of(raw: Path) -> pd.Timestamp:
    as_of = as_of_from_rows(_read(raw / "Module Deliveries.csv"))
    if as_of is None:
        raise ValueError("No 'As of' data date in the Module Deliveries header")
    return as_of


# Header text (newlines collapsed) -> column name used downstream.
MD_COLUMNS = {
    "Sr": "sr", "Project": "project", "P6 Name": "p6_name", "SPV": "spv", "Plot": "plot",
    "Category": "category", "Type": "vendor_type", "MMS Type": "mms_type",
    "AGEL / EPC": "epc_cell", "Priority": "priority", "OL": "ol",
    "Capacity (MWac)": "capacity_mwac", "Capacity (MWp)": "capacity_mwp",
    "Connectivity Phase": "connectivity_phase", "LTA": "lta", "SCOD": "scod", "AOP (Plan)": "aop",
    "Ordered (MWp)": "ordered_mwp", "Balance Ordering (MWp)": "balance_mwp",
    "Total Receipt (MWp)": "receipt_mwp", "Erection done (MWp)": "erection_mwp",
    "Module Inventory (MWp)": "inventory_mwp", "Under Transit (MWp)": "transit_mwp",
    "Ariba matched by (plant / PO)": "ariba_match", "Received · Ariba (MWp)": "ariba_received_mwp",
    "Last receipt (GRN date)": "last_grn", "Dispatched, no GRN (MWp)": "dispatched_no_grn_mwp",
    "Finance checklist (raised / due)": "finance_checklist",
    "Piles installed (%)": "piles_pct", "Structure built (tracker, %)": "structure_pct",
    "Modules mounted (%)": "modules_pct", "Behind plan (P6 baseline, points)": "behind_plan_pts",
    "Structure ready, no modules (MWdc)": "structure_ready_no_modules_mwdc",
    "Module supply vs site": "supply_vs_site", "FTC forecast (site speed)": "ftc_forecast_cell",
    "Monthly plan timed by": "plan_timed_by", "Balance Dispatch (MWp)": "balance_dispatch_mwp",
    "Status": "status", "FTC Date": "ftc_cell", "TC Date": "tc_cell", "Module Date": "module_cell",
    "PO Placed (Actual)": "po_placed_cell", "First Dispatch (Ariba IBD)": "first_dispatch",
    "Ariba deliveries by PO (dispatch → receipt · lots in the Ariba Ledger sheet)": "ariba_lots_cell",
    "Remarks": "remarks",
}
NUMERIC = ["ol", "capacity_mwac", "capacity_mwp", "ordered_mwp", "balance_mwp", "receipt_mwp",
           "erection_mwp", "inventory_mwp", "transit_mwp", "ariba_received_mwp",
           "dispatched_no_grn_mwp", "piles_pct", "structure_pct", "modules_pct",
           "behind_plan_pts", "structure_ready_no_modules_mwdc", "balance_dispatch_mwp"]
DATES = ["lta", "scod", "aop", "last_grn", "first_dispatch"]


def parse_module_deliveries(raw: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per P6 project, plus the rule engine's month-wise plan (long)."""
    md, plan = parse_module_deliveries_rows(_read(raw / "Module Deliveries.csv"))
    return md.drop(columns="_line"), plan


def header_index(rows: list[list[str]]) -> int:
    i = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Sr" and "Project" in r), None)
    if i is None:
        raise ValueError("no header row starting 'Sr', 'Project', ... (Module Deliveries layout)")
    return i


def parse_module_deliveries_rows(rows: list[list[str]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """As parse_module_deliveries, from rows already read (an uploaded file).
    Each record keeps its line in `rows` as `_line`."""
    hdr_i = header_index(rows)
    header = [re.sub(r"\s+", " ", h).strip() for h in rows[hdr_i]]
    sub = rows[hdr_i + 1]
    month_cols = {i: sub[i] for i in range(len(sub)) if re.fullmatch(r"[A-Z][a-z]{2}-\d{2}", sub[i] or "")}

    records, plan, group = [], [], None
    for line, r in enumerate(rows[hdr_i + 2:], start=hdr_i + 2):
        if not r or not any(c.strip() for c in r):
            continue
        r = r + [""] * (len(header) - len(r))
        first = r[0].strip()
        if not first and r[1].startswith("Total"):
            break
        if not first.isdigit():
            # EPC group row: "Bondada Energy Limited   (6 projects · 979.1 MWp)"
            m = re.match(r"(.+?)\s{2,}\(", first)
            group = m.group(1).strip() if m else first
            continue
        rec = {MD_COLUMNS[h]: r[i].strip() for i, h in enumerate(header) if h in MD_COLUMNS}
        rec["epc_group"] = group
        rec["row_id"] = len(records)
        rec["_line"] = line
        for i, mon in month_cols.items():
            for mwp, mwac in re.findall(r"\[\s*([\d.]+)\s*/\s*([\d.]+)\s*\]", r[i]):
                plan.append({"row_id": rec["row_id"], "month": pd.to_datetime(mon, format="%b-%y"),
                             "plan_mwp": float(mwp), "plan_mwac": float(mwac)})
        records.append(rec)

    if not records:
        raise ValueError("no project rows (rows whose 'Sr' is a number) below the header")
    md = pd.DataFrame(records)
    for c in MD_COLUMNS.values():   # a partial upload: absent columns stay missing
        if c not in md:
            md[c] = ""
    for c in NUMERIC:
        md[c] = md[c].map(to_num)
    for c in DATES:
        md[c] = md[c].map(to_date)

    # FTC forecast at site speed: '23-May-27 (+182d, Structure built (tracker))',
    # '10-Aug-26 (on time)', 'Too slow to forecast', ''.
    cell = md["ftc_forecast_cell"].fillna("")
    md["site_ftc_forecast"] = cell.map(to_date)
    md["site_ftc_delay_days"] = cell.map(
        lambda s: float(m.group(1)) if (m := re.search(r"\(([+-]\d+)d", s)) else (0.0 if "on time" in s else np.nan))
    md["site_ftc_basis"] = cell.map(lambda s: m.group(1).strip() if (m := re.search(r"d, (.+)\)$", s)) else None)
    md["site_too_slow"] = cell.str.contains("Too slow", na=False)

    # PO placed (actual): '19-Jun-26 (+25d)' — the earliest SAP PO for the project.
    md["po_placed"] = md["po_placed_cell"].map(to_date)

    # Remarks: the rule engine's own verdicts, kept as structured flags.
    rm = md["remarks"].fillna("")
    md["rule_shortfall_days"] = rm.map(lambda s: max(map(float, re.findall(r"up to (\d+) days short", s)), default=np.nan))
    md["rule_site_late_days"] = rm.map(
        lambda s: float(m.group(1)) if (m := re.search(r"too late for the P6 FTC \(up to (\d+) days\)", s)) else np.nan)
    md["rule_ftc_past_lta"] = rm.str.contains("FTC PAST LTA", na=False)
    md["rule_quota_pushed"] = rm.str.contains("quota was exhausted", na=False)
    md["rule_capacity_delayed_past_lta"] = rm.str.contains("delay beyond the LTA", na=False)
    md["rule_overdue_order"] = rm.str.contains("already passed its own ordering date", na=False)
    md["rule_records_gap"] = rm.str.contains("records gap", na=False)
    md["all_phases_charged"] = md["ftc_cell"].str.contains("No pending FTC", na=False)
    return md, pd.DataFrame(plan)


PHASE_LINE = re.compile(
    rf"^(?P<label>Ph[^(:]*)(?:\((?P<mw>[\d.]+)\s*MW\))?(?P<extra>[^:]*):\s*(?P<date>{DATE_RE})$")


def explode_phases(md: pd.DataFrame) -> pd.DataFrame:
    """One row per (project, phase) from the multi-line FTC / TC / Module cells.

    The three cells list phases in the same order, so line i of each belongs to
    the same phase. A single bare date means the project is one phase.
    """
    out = []
    for _, r in md.iterrows():
        ftc_lines = [l.strip() for l in (r["ftc_cell"] or "").split("\n") if l.strip()]
        tc_lines = [l.strip() for l in (r["tc_cell"] or "").split("\n") if l.strip()]
        mod_lines = [l.strip() for l in (r["module_cell"] or "").split("\n") if l.strip()]
        if not ftc_lines or "No pending FTC" in ftc_lines[0]:
            continue
        for k, line in enumerate(ftc_lines):
            m = PHASE_LINE.match(line)
            if m:
                label = re.sub(r"\s+", " ", m.group("label") + m.group("extra")).strip()
                mw = float(m.group("mw")) if m.group("mw") else np.nan
            elif re.fullmatch(DATE_RE, line):
                label, mw = "Single phase", r["capacity_mwac"]
            else:
                continue
            out.append({
                "row_id": r["row_id"], "phase": label, "phase_idx": k,
                "n_phases": len(ftc_lines), "phase_mwac": mw,
                "ftc_date": to_date(line),
                "tc_date": to_date(tc_lines[k]) if k < len(tc_lines) else pd.NaT,
                "rule_module_date": to_date(mod_lines[k]) if k < len(mod_lines) else pd.NaT,
            })
    return pd.DataFrame(out)


# ── Ariba ledger ─────────────────────────────────────────────────────────────

def parse_ariba(raw: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Dispatch/receipt lots, de-duplicated across WBS capacity shares.

    A plant shared by two projects appears once per project with Qty split by
    capacity share (25% / 75%, 85% / 15%). Those rows are one physical lot, so
    they are merged and their quantities summed.
    """
    df = pd.read_csv(raw / "Ariba Ledger.csv", dtype=str, encoding="utf-8-sig").fillna("")
    df["po_date"] = df["PO date (SAP)"].map(to_date)
    df["dispatch_date"] = df["Dispatched (IBD)"].map(to_date)
    df["grn_date"] = df["Received (GRN)"].map(to_date)
    df["qty"] = df["Qty"].map(to_num)
    df["mwp"] = df["MWp"].map(to_num)
    df["in_ariba"] = df["Status"] != "Not in Ariba extract"
    df["ordered_mwp_sap"] = df["Match rule"].map(
        lambda s: float(m.group(1)) if (m := re.search(r"\(([\d.]+) MWp ordered in SAP\)", s)) else np.nan)

    lots = df[df["in_ariba"]]
    key = ["PO", "Line(s)", "Dispatched (IBD)", "Received (GRN)", "Checklist no.", "Vendor", "Ariba plant"]
    lots = (lots.groupby(key, dropna=False, sort=False)
            .agg(projects=("Project", lambda s: " | ".join(sorted(set(s)))),
                 po_date=("po_date", "first"), dispatch_date=("dispatch_date", "first"),
                 grn_date=("grn_date", "first"), status=("Status", "first"),
                 qty=("qty", "sum"), mwp=("mwp", "sum"), n_share_rows=("Project", "size"))
            .reset_index()
            .rename(columns={"PO": "po", "Vendor": "vendor", "Ariba plant": "plant", "Line(s)": "po_lines"}))

    open_pos = (df[~df["in_ariba"]]
                .groupby(["PO", "Vendor"], sort=False)
                .agg(projects=("Project", lambda s: " | ".join(sorted(set(s)))),
                     po_date=("po_date", "first"), ordered_mwp_sap=("ordered_mwp_sap", "sum"))
                .reset_index().rename(columns={"PO": "po", "Vendor": "vendor"}))
    return lots, open_pos


def vendor_origin(vendor: str, po: str) -> str:
    """Where the modules come from, read from the supplier and the PO series.

    5310xxxxxx POs are imports; 4510xxxxxx are domestic. Jinko Vietnam is the
    only South-East-Asian supplier in the ledger. Domestic suppliers cannot be
    split into ALMM vs DCR from the ledger alone.
    """
    v = vendor.upper()
    if "VIETNAM" in v:
        return "SEA"
    if po.startswith("531"):
        return "China"
    return "Domestic"


# ── Site productivity ────────────────────────────────────────────────────────

def parse_site_productivity(raw: Path) -> pd.DataFrame:
    """One row per project block: the three 'total, in module MWdc' rows.

    Blocks appear in the same order as the Module Deliveries project rows, so
    the k-th block belongs to row_id k (checked by name in build_datasets).
    """
    df = pd.read_csv(raw / "Site Productivity.csv", dtype=str, encoding="utf-8-sig").fillna("")
    df.columns = [re.sub(r"\s+", " ", c).strip() for c in df.columns]
    tot = df[(df["Code"] == "") & df["Activity"].str.contains("total, in module MWdc")]
    blocks, cur = [], None
    for _, r in tot.iterrows():
        if r["Area"] == "Piles installed":
            cur = {"sp_project": r["Project"], "mms_type_sp": r["MMS type"],
                   "p6_data_date": to_date(r["P6 data date"]), "p6_final_ftc": to_date(r["Final FTC (P6)"]),
                   "scope_mwdc": to_num(r["Scope"])}
            blocks.append(cur)
        key = {"Piles installed": "piles", "Structure built (tracker)": "structure",
               "Modules mounted": "modules"}[r["Area"]]
        cur[f"{key}_done_mwdc"] = to_num(r["Done"])
        cur[f"{key}_planned_pct"] = to_num(r["Planned % (P6 baseline)"])
        cur[f"{key}_pace_per_day"] = to_num(r["Pace / day (average since start)"])
        cur[f"{key}_needed_per_day"] = to_num(r["Needed / day (to final FTC)"])
        cur[f"{key}_manpower_needed"] = to_num(r["Manpower / day needed"])
        if key == "modules":
            cur["modules_finish_at_pace"] = to_date(r["Finish at pace (estimate)"])
    sp = pd.DataFrame(blocks)
    sp["sp_block"] = range(len(sp))
    return sp
