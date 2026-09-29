"""
BESS EAC (Estimate at Completion), per project, on the approved EAC format
(Data/EAC_BEES/EAC Format_AND_WBS Structure.xlsx, sheet "PSS 09_EAC_WBS Mapped").

Columns, the same rule on every row (user, 2026-09-29 - the one-off cell
adjustments in the source sheet, x1.0825 / 18% / x1.18 / typed EAC values,
are deliberately not carried over):

    Approved Capex        editable; pre-filled from the project's CAPEX sheet
    Incurred              SAP CJI3 "Val/COArea Crcy" on the row's WBS,
                          excluding Value Type 11 (stock-side postings - the
                          EAC's own actuals never contained them)
    Committed             SAP S_ALR_87013558 "Val/COArea Crcy" on the row's WBS,
                          purchase orders (POrd) only
    Balance to Completion editable
    EAC                   Incurred + Committed + Balance to Completion
    Variance              Approved Capex - EAC
    Remarks               editable

Group rows and the two totals are sums of their items. A row's WBS is stored as
a suffix (-01-01 = BESS Containers) and matched in ALL THREE companies - AGEL,
AGE6L and SPV share one activity-code structure (WBS Structure Baseline sheet),
and PSS-11 / PSS-12 book their container POs on the SPV (H-6074-01-01), which
the PSS-09-built sheet had only mapped to AGEL. A WBS matches itself and
anything below it (-05 covers -05-01), as SAP's WBS hierarchy rolls up.
SAP cost on a WBS no row maps (-18 ... -23 on the PSS-11 / 12 SPVs) is shown on
its own "Other SAP cost" row with its codes, so totals never drop it.
"""
from __future__ import annotations

import glob
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EAC_DIR = os.path.join(REPO, "Data", "EAC_BEES")
WORKBOOK = "EAC Format_AND_WBS Structure.xlsx"

# Project -> the three company WBS roots (from the workbook's "SAP Working").
ROOTS: Dict[str, Dict[str, str]] = {
    "AGE27BL_PSS11_FINAL": {"agel": "H-5XA1", "age6l": "H-63A1", "spv": "H-6074"},
    "AGE27CL_PSS12_FINAL": {"agel": "H-5XA2", "age6l": "H-63A2", "spv": "H-6764"},
    "ARE35L_PSS10B_FINAL": {"agel": "H-51X9", "age6l": "H-63X9", "spv": "H-51N2"},
    "AGE27AL_PSS09_FINAL": {"agel": "H-5XWG", "age6l": "H-63WG", "spv": "H-6497"},
    "AGE44L_PSS5B_FINAL": {"agel": "H-5XWD", "age6l": "H-63WD", "spv": "H-51I4"},
    "AGE35L_PSS8B_FINAL": {"agel": "H-5XWF", "age6l": "H-63WF", "spv": "H-51N3"},
}
# Project -> its sheet of approved capex in the workbook. PSS-11 has none.
CAPEX_SHEETS = {
    "AGE27CL_PSS12_FINAL": "PSS 12_CAPEX ",
    "ARE35L_PSS10B_FINAL": "PSS 10_CAPEX",
    "AGE27AL_PSS09_FINAL": "PSS 09_CAPEX",
    "AGE44L_PSS5B_FINAL": "PSS 05_CAPEX",
    "AGE35L_PSS8B_FINAL": "PSS 08_CAPEX",
}

# (key, Sr No, description, WBS as (company, suffix)), in the EAC sheet's order.
TEMPLATE: List[Tuple[str, str, str, tuple]] = [
    ('L01', '1', 'Battery Containers (2 Hour system)', (('agel', '-01-01'), ('agel', '-01-02'))),
    ('L02', '2', 'PCS (2 Hour system)', (('agel', '-02-01'), ('agel', '-02-02'))),
    ('L03', '3', 'EMS (2 Hour system)', (('agel', '-03-01'), ('agel', '-03-02'))),
    ('L04', '3.1', 'Battery + PCS + EMS', ()),
    ('L05', '4', 'Transformer & NIFPS', (('agel', '-04'), ('age6l', '-04'))),
    ('L06', '5', 'BOS Elec', ()),
    ('L07', '5.1', 'HT Panel', (('agel', '-06-01'), ('age6l', '-06-01'))),
    ('L08', '5.2', 'DC LT Cable', (('agel', '-06-02'), ('age6l', '-06-02'))),
    ('L09', '5.3', 'HT Cable', (('agel', '-06-03'), ('age6l', '-06-03'))),
    ('L10', '5.4', 'Scada Cable & FO', (('agel', '-06-05'), ('age6l', '-06-05'))),
    ('L11', '5.5', 'ACDC/ Electrical Erection & Fire Alarm system', (('agel', '-06-04'), ('age6l', '-06-04'), ('agel', '-06-06'))),
    ('L12', '6', 'Installation and Comissioning', (('age6l', '-05-01'), ('age6l', '-05-02'), ('age6l', '-05-03'))),
    ('L13', '7', 'BOP Civil', ()),
    ('L14', '7.1', 'Battery container', (('age6l', '-08-01-01'),)),
    ('L15', '7.2', 'Transformer', (('age6l', '-08-01-02'),)),
    ('L16', '7.3', 'Civil of PCS', (('age6l', '-08-01-03-01'),)),
    ('L17', '7.4', 'Structure of PCS', (('age6l', '-08-01-03-02'),)),
    ('L18', '7.5', 'CSS', (('age6l', '-08-01-04'),)),
    ('L19', '7.6', 'Civil of MCR', (('age6l', '-08-01-05-01'),)),
    ('L20', '7.7', 'Structure of MCR', (('age6l', '-08-01-05-02'),)),
    ('L21', '7.8', 'Civil of SGR', (('age6l', '-08-01-06-01'),)),
    ('L22', '7.9', 'Structure of SGR', (('age6l', '-08-01-06-02'),)),
    ('L23', '7.10', 'Bund', (('age6l', '-08-02-01'),)),
    ('L24', '7.11', 'Earth work', (('age6l', '-08-02-02'),)),
    ('L25', '7.12', 'Roads', (('age6l', '-08-03'),)),
    ('L26', '7.13', 'Area Grading', (('age6l', '-08-04'),)),
    ('L27', '7.14', 'Boundary wall and Fencing', (('age6l', '-08-05'),)),
    ('L28', '8', 'Spares', (('agel', '-13'),)),
    ('L29', '9', 'Consultancy Charges', (('spv', '-07-01'), ('spv', '-07-02'), ('spv', '-07-03'), ('spv', '-07-04'))),
    ('L30', '10', 'ISA', (('spv', '-09-01'), ('spv', '-09-02'), ('spv', '-09-03'), ('spv', '-09-04'))),
    ('L31', '11', 'Taxes & Duties', ()),
    ('L32', 'A', 'A. Total Hard Cost', ()),
    ('L33', '12', 'Pre Ops', ()),
    ('L34', '12.01', 'Construction Power', (('spv', '-10-01'),)),
    ('L35', '12.02', 'Area Lighting', (('spv', '-10-02'),)),
    ('L36', '12.03', 'Site Office & Store Setup', (('spv', '-10-03'),)),
    ('L37', '12.04', 'Guest house / Office set up', (('spv', '-10-04'),)),
    ('L38', '12.05', 'Administration and Office Expenses', (('spv', '-10-05'),)),
    ('L39', '12.06', 'Vehicle Running', (('spv', '-10-06'),)),
    ('L40', '12.07', 'HSE', (('spv', '-10-07'),)),
    ('L41', '12.08', 'Security', (('spv', '-10-08'),)),
    ('L42', '12.09', 'IT Infrastructure', (('spv', '-10-09'),)),
    ('L43', '12.10', 'Manpower & Equipment Hiring', (('spv', '-10-10'),)),
    ('L44', '12.11', 'Professional & Consultancy Fees', (('spv', '-10-11'),)),
    ('L45', '12.12', 'Rates & Taxes', (('spv', '-10-12'),)),
    ('L46', '12.13', 'Quality Charges', (('spv', '-10-13'),)),
    ('L47', '12.14', 'Geo Tech Charges', (('spv', '-10-14'),)),
    ('L48', '12.15', 'Commissioning Manpower', (('spv', '-10-15'),)),
    ('L49', '12.16', 'Insurance', (('spv', '-10-16'),)),
    ('L50', '12.17', 'Corporate Allocation', (('spv', '-10-17'),)),
    ('L51', '12.18', 'RLDC Registration Fees', (('spv', '-10-18-01'),)),
    ('L52', '12.19', 'GNA Charges', (('spv', '-10-18-02'),)),
    ('L53', '12.20', 'Misc Charges (GEDA MOOWER)', (('spv', '-10-18-03'),)),
    ('L54', '12.21', 'BOCW & CLRA', (('spv', '-10-18-04'),)),
    ('L55', '12.22', 'Bid & Success Fee', (('spv', '-10-19'),)),
    ('L56', '12.23', 'Depreciation', (('spv', '-10-20'),)),
    ('L57', '13', 'Financing & IDC', ()),
    ('L58', '13.1', 'Financing', (('spv', '-11-02'),)),
    ('L59', '13.2', 'IDC', (('spv', '-11-04'),)),
    ('L60', '13.3', 'Interest Income - Outside', (('spv', '-11-07'),)),
    ('L61', '14', 'PMC Fees', (('spv', '-12'),)),
    ('L62', '15', 'Contingency', (('spv', '-14'),)),
    ('L64', '16', 'Other SAP cost (WBS not in EAC format)', ()),
    ('L63', 'B', 'B. Total Cost', ()),
]
# Sum rows and what they sum.
GROUPS: Dict[str, List[str]] = {
    "L04": ["L01", "L02", "L03"],
    "L06": ["L07", "L08", "L09", "L10", "L11"],
    "L13": [f"L{i:02d}" for i in range(14, 28)],
    "L33": [f"L{i:02d}" for i in range(34, 57)],
    "L57": ["L58", "L59", "L60"],
    "L32": ["L04", "L05", "L06", "L12", "L13", "L28", "L29", "L30", "L31"],
    "L63": ["L32", "L33", "L57", "L61", "L62", "L64"],
}
TOTALS = {"L32", "L63"}
# BOP Civil and Pre-Ops are broken down differently in the CAPEX sheets, so
# their approved figure can be held on the group row until items are entered.
GROUP_APPROVED_EDITABLE = {"L13", "L33"}
# CAPEX-sheet Sr No for each row pre-filled from it.
CAPEX_SR = {"L01": "1", "L02": "2", "L03": "3", "L05": "4", "L07": "5.1", "L08": "5.2",
            "L09": "5.3", "L10": "5.4", "L11": "5.5", "L12": "6", "L13": "7", "L28": "8",
            "L29": "9", "L30": "10", "L31": "11", "L33": "12", "L58": "13.1", "L59": "13.2",
            "L61": "14", "L62": "15"}


def _newest(pattern: str) -> Optional[str]:
    hits = [p for p in glob.glob(os.path.join(EAC_DIR, pattern)) if not os.path.basename(p).startswith("~$")]
    return max(hits, key=os.path.getmtime) if hits else None


def ingest_eac_sap(db: Session, incurred_path: str = None, committed_path: str = None) -> Dict[str, Any]:
    """Replace bess_eac_sap_line from the newest CJI3 (Incurred) and
    S_ALR_87013558 (Committed) extracts in Data/EAC_BEES."""
    import models
    incurred_path = incurred_path or _newest("CJI3*.xls*")
    committed_path = committed_path or _newest("S_[Aa][Ll][Rr]*.xls*")
    if not incurred_path or not committed_path:
        raise FileNotFoundError("CJI3 and S_ALR_87013558 extracts are both needed in Data/EAC_BEES")

    rows, now = [], datetime.utcnow()
    a = pd.read_excel(incurred_path, dtype=str)
    a["v"] = pd.to_numeric(a["Val/COArea Crcy"], errors="coerce").fillna(0.0)
    a["wbs"] = a["WBS Element"].fillna("").str.strip()
    a["vt"] = a.get("Value Type", pd.Series("", index=a.index)).fillna("").str.strip()
    kept = a[(a["wbs"] != "") & (a["vt"] != "11") & (a["v"] != 0)]
    a_doc = kept.get("Purchasing Document", pd.Series("", index=kept.index)).fillna("").str.strip()
    for wbs, v, vt, doc in zip(kept["wbs"], kept["v"], kept["vt"], a_doc):
        rows.append(dict(kind="incurred", wbs_element=wbs, value_inr=float(v), value_type=vt or None,
                         document=doc or None, source_file=os.path.basename(incurred_path), upload_time=now))
    c = pd.read_excel(committed_path, dtype=str)
    c["v"] = pd.to_numeric(c["Val/COArea Crcy"], errors="coerce").fillna(0.0)
    c["wbs"] = c["WBS Element"].fillna("").str.strip()
    c["cat"] = c["Reference document category"].fillna("").str.strip()
    ckept = c[(c["wbs"] != "") & (c["cat"] == "POrd") & (c["v"] != 0)]
    c_doc = ckept.get("Ref Document Number", pd.Series("", index=ckept.index)).fillna("").str.strip()
    for wbs, v, cat, doc in zip(ckept["wbs"], ckept["v"], ckept["cat"], c_doc):
        rows.append(dict(kind="committed", wbs_element=wbs, value_inr=float(v), ref_category=cat,
                         document=doc or None, source_file=os.path.basename(committed_path), upload_time=now))
    db.query(models.BESSEACSapLine).delete()
    db.bulk_insert_mappings(models.BESSEACSapLine, rows)
    db.commit()
    pdates = pd.to_datetime(a["Posting Date"], errors="coerce")
    return {"incurred_file": os.path.basename(incurred_path), "committed_file": os.path.basename(committed_path),
            "incurred_lines": int(len(kept)), "committed_lines": int(len(ckept)),
            "incurred_excluded_stock_lines": int((a["vt"] == "11").sum()),
            "committed_excluded_preq_lines": int((c["cat"] == "PReq").sum()),
            "incurred_posting_from": str(pdates.min().date()) if pdates.notna().any() else None,
            "incurred_posting_to": str(pdates.max().date()) if pdates.notna().any() else None}


def capex_seed(project_id: str) -> Dict[str, float]:
    """Line key -> approved capex (INR Cr) from the project's CAPEX sheet."""
    sheet = CAPEX_SHEETS.get(project_id)
    path = os.path.join(EAC_DIR, WORKBOOK)
    if not sheet or not os.path.exists(path):
        return {}
    import openpyxl
    ws = openpyxl.load_workbook(path, data_only=True, read_only=False)[sheet]
    col = next((c for r in range(3, 8) for c in range(1, ws.max_column + 1)
                if isinstance(ws.cell(r, c).value, str) and "INR-Cr" in ws.cell(r, c).value), None)
    if col is None:
        return {}
    by_sr: Dict[str, float] = {}
    for r in range(7, ws.max_row + 1):
        sr, v = ws.cell(r, 1).value, ws.cell(r, col).value
        if sr is not None and isinstance(v, (int, float)):
            by_sr.setdefault(str(sr).strip(), float(v))
    return {key: by_sr[sr] for key, sr in CAPEX_SR.items() if sr in by_sr}


def _suffixes(wbs: tuple) -> List[str]:
    out: List[str] = []
    for _company, suffix in wbs:
        if suffix not in out:
            out.append(suffix)
    return out


def _codes(project_id: str, wbs: tuple) -> List[str]:
    """The row's WBS in every company of the project."""
    roots = ROOTS[project_id]
    return [root + suffix for suffix in _suffixes(wbs) for root in roots.values()]


def build(db: Session, project_id: str) -> Dict[str, Any]:
    """The EAC table for one BESS project, every figure computed on read."""
    import models
    if project_id not in ROOTS:
        raise KeyError(project_id)
    roots = ROOTS[project_id]
    sap = db.execute(text(
        "select kind, wbs_element, sum(value_inr) from bess_eac_sap_line "
        "where left(wbs_element, 6) = any(:r) group by 1, 2"), {"r": list(roots.values())}).fetchall()
    sap_meta = db.execute(text(
        "select kind, max(source_file), max(upload_time) from bess_eac_sap_line group by 1")).fetchall()
    entries = {e.line_key: e for e in db.query(models.BESSEACEntry).filter(
        models.BESSEACEntry.project_id == project_id)}
    seed = capex_seed(project_id)

    def sap_sum(kind: str, codes: List[str]) -> float:
        total = 0.0
        for k, wbs, v in sap:
            if k == kind and any(wbs == c or wbs.startswith(c + "-") for c in codes):
                total += float(v or 0)
        return total / 1e7

    cr = lambda x: None if x is None else round(x, 4)
    # SAP WBS no template row maps - shown on L64 so the totals keep them.
    mapped = [c for _k, _s, _d, w in TEMPLATE for c in _codes(project_id, w)]
    unmapped = sorted({wbs for _k, wbs, _v in sap
                       if not any(wbs == c or wbs.startswith(c + "-") for c in mapped)})
    rows: Dict[str, Dict[str, Any]] = {}
    for key, sr, desc, wbs in TEMPLATE:
        e = entries.get(key)
        codes = unmapped if key == "L64" else _codes(project_id, wbs)
        approved = e.approved_capex_cr if (e and e.approved_capex_cr is not None) else seed.get(key)
        rows[key] = {
            "key": key, "sr": sr, "description": desc,
            "kind": "total" if key in TOTALS else ("group" if key in GROUPS else "item"),
            "wbs": ({c: [w for w in unmapped if w.startswith(roots[c])] for c in ("agel", "age6l", "spv")}
                    if key == "L64" else
                    {c: [roots[c] + s for s in _suffixes(wbs)] for c in ("agel", "age6l", "spv")}),
            "approved": approved,
            "approvedSource": ("edited" if (e and e.approved_capex_cr is not None)
                               else "capex sheet" if key in seed else None),
            "incurred": sap_sum("incurred", codes) if codes else 0.0,
            "committed": sap_sum("committed", codes) if codes else 0.0,
            "balance": (e.balance_cr if e and e.balance_cr is not None else 0.0),
            "remarks": e.remarks if e else None,
            "updatedBy": e.updated_by if e else None,
            "editable": {"approved": key not in GROUPS or key in GROUP_APPROVED_EDITABLE,
                         "balance": key not in GROUPS, "remarks": True},
        }

    def roll(key: str) -> None:
        if key not in GROUPS:
            return
        kids = GROUPS[key]
        for k in kids:
            roll(k)
        r = rows[key]
        for col in ("incurred", "committed", "balance"):
            r[col] = sum(rows[k][col] or 0 for k in kids)
        kid_approved = [rows[k]["approved"] for k in kids if rows[k]["approved"] is not None]
        if key in GROUP_APPROVED_EDITABLE and not kid_approved:
            pass   # keep the group's own figure (edited or CAPEX) until items carry theirs
        else:
            r["approved"] = sum(kid_approved) if kid_approved else None
            r["approvedSource"] = "sum of items" if kid_approved else None

    for key in ("L32", "L33", "L57", "L63"):
        roll(key)
    for r in rows.values():
        r["eac"] = (r["incurred"] or 0) + (r["committed"] or 0) + (r["balance"] or 0)
        r["variance"] = (r["approved"] - r["eac"]) if r["approved"] is not None else None
        for col in ("approved", "incurred", "committed", "balance", "eac", "variance"):
            r[col] = cr(r[col])
    return {
        "projectId": project_id, "roots": roots,
        "rows": [rows[k] for k, *_ in TEMPLATE],
        "sources": {k: {"file": f, "loadedAt": t.isoformat() if t else None} for k, f, t in sap_meta},
        "basis": {
            "incurred": "SAP CJI3 Val/COArea Crcy on the row's WBS and below; Value Type 11 (stock-side) excluded",
            "committed": "SAP S_ALR_87013558 Val/COArea Crcy on the row's WBS and below; purchase orders (POrd) only",
            "eac": "Incurred + Committed + Balance to Completion",
            "variance": "Approved Capex - EAC",
            "unit": "INR Cr",
        },
    }


def save_entry(db: Session, project_id: str, key: str, body: Dict[str, Any]) -> None:
    """Store the editable columns of one row. Only fields present in `body`
    change; null clears an override (Approved falls back to the CAPEX sheet)."""
    import models
    if project_id not in ROOTS or key not in {k for k, *_ in TEMPLATE}:
        raise KeyError(key)
    if key in GROUPS and key not in GROUP_APPROVED_EDITABLE and "approved" in body:
        raise ValueError("Approved Capex on this row is the sum of its items")
    if key in GROUPS and "balance" in body:
        raise ValueError("Balance to Completion on a group row is the sum of its items")
    e = db.query(models.BESSEACEntry).filter(models.BESSEACEntry.project_id == project_id,
                                            models.BESSEACEntry.line_key == key).first()
    if e is None:
        e = models.BESSEACEntry(project_id=project_id, line_key=key)
        db.add(e)
    for field, col in (("approved", "approved_capex_cr"), ("balance", "balance_cr")):
        if field in body:
            v = body[field]
            setattr(e, col, None if v in (None, "") else float(v))
    if "remarks" in body:
        e.remarks = (body["remarks"] or "").strip() or None
    e.updated_by = body.get("updatedBy")
    e.updated_at = datetime.utcnow()
    db.commit()
