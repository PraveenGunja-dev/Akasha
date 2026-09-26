"""
Procurement's Packages-through-PO-Date columns, from the WBS mapping BESS
PMAG uploads (per Divyanshi Tahkit's mail, 2026-09-22): Packages/WBS baseline
per project, joined to the ZPS021 PO dump (T-code ZPS021, not the ZPSPS007
extract mt_poamount already syncs).

Confirmed against the live database (2026-09-26): mt_poamount already carries
this same WBS-level PO data (material_name, vendor_name, po_quantities,
purchasing_document) - except `document_date` is null on every one of the six
BESS WBS prefixes' 341+336+350+376+247 lines, though it is populated
elsewhere in the same extract. PO Date is the one field this upload actually
adds; by the user's own instruction (2026-09-26) it - and the rest of this
column group - comes from this upload only, never from P6.

Stored as real tables (mt_zps021, cpag_wbs_baseline), not a JSON blob: this is
recurring transactional data the team will re-upload as a fresh full dump
each time, the same shape as the ZPSPS007 sync's own mt_poamount, and worth
having queryable the same way (user decision 2026-09-26 - "we need to store
zps021 data in the DB", BESS-project-UI use of it deferred for later).

One PO under a package is one row (BESS PMAG's own instruction, given for
SCADA & FO Cable Supply): a package with three POs prints three rows.
"Scope"/"Ordering Completed" sum only the PO's line items sharing its most
common unit - a transformer PO's accessory lines (bushings in EA, gaskets in
SET) are not the transformer count and must not be added into it.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime
from io import BytesIO
from typing import Any, Dict, List, Optional

import openpyxl
from sqlalchemy import text
from sqlalchemy.orm import Session

DUMP_SHEET = "ZPS021-Dump"
BASELINE_PREFIX = "wbs baseline"

# ZPS021 order-unit code -> the pack's own UOM spelling, and whether the
# summed quantity needs converting into that unit (SAP books cable in
# metres; the pack prints kilometres, as every other CPAG cable row does).
UOM_MAP = {"M": ("Kms", 1000.0), "MT": ("Kms", 1000.0), "EA": ("Nos.", 1.0),
          "NO": ("Nos.", 1.0), "SET": ("Set", 1.0), "AU": ("Lot", 1.0),
          "LOT": ("Lot", 1.0), "M2": ("Sqm", 1.0), "PAC": ("Pack", 1.0),
          "L": ("Ltr", 1.0)}

# The top-level item's own description always starts with this word,
# verified against the file (2026-09-26) - a mixed-unit PO sums only the
# lines starting with it, not every line sharing its unit (a transformer PO
# also books bushings, gaskets and relays in the same "EA").
MAIN_ITEM_KEYWORD = {
    "Converter Transformer": "transformer",
    "HT Panel Supply (MV Switchgear)": "panel",
    "EMS Supply": "energy management",
}


def _clean(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _pss_key_from_sheet(name: str) -> Optional[str]:
    """"WBS Baseline PSS10 (B)" -> "10B" - the same short key
    cpag_pptx.pss_key() derives from a project's own "PSS-10(B)"."""
    m = re.search(r"PSS\s*(\d+)\s*\(?\s*([A-Za-z]?)\s*\)?", name, re.I)
    if not m:
        return None
    return m.group(1) + m.group(2).upper()


def _read_baselines(wb) -> Dict[str, List[Dict[str, Any]]]:
    out: Dict[str, List[Dict[str, Any]]] = {}
    for name in wb.sheetnames:
        if not name.lower().startswith(BASELINE_PREFIX):
            continue
        pss = _pss_key_from_sheet(name)
        if not pss:
            continue
        ws = wb[name]
        pkgs = []
        for row in ws.iter_rows(min_row=2, max_col=3, values_only=True):
            label, wbs = _clean(row[1]), _clean(row[2])
            if not label or not wbs:
                continue
            pkgs.append({"package": label, "wbs": wbs})
        out[pss] = pkgs
    return out


def _read_dump(wb) -> List[Dict[str, Any]]:
    if DUMP_SHEET not in wb.sheetnames:
        raise ValueError(f"No '{DUMP_SHEET}' sheet found - this needs to be the "
                         f"ZPS021 dump workbook (found: {', '.join(wb.sheetnames)}).")
    ws = wb[DUMP_SHEET]
    rows_iter = ws.iter_rows(values_only=True)
    head = [_clean(v) for v in next(rows_iter)]
    need = ["Project Definition", "WBS Element", "Description", "Document Date",
            "Vendor name", "Purchasing Document", "Item", "Item Description",
            "Order Unit", "Order Quantity"]
    missing = [n for n in need if n not in head]
    if missing:
        raise ValueError(f"'{DUMP_SHEET}' is missing column(s): {', '.join(missing)}.")
    idx = {h: i for i, h in enumerate(head)}

    out = []
    for row in rows_iter:
        wbs = _clean(row[idx["WBS Element"]])
        if not wbs:
            continue
        date = row[idx["Document Date"]]
        out.append({
            "project_definition": _clean(row[idx["Project Definition"]]),
            "wbs_element": wbs,
            "description": _clean(row[idx["Description"]]),
            "document_date": date if isinstance(date, datetime) else None,
            "vendor_name": _clean(row[idx["Vendor name"]]),
            "purchasing_document": _clean(row[idx["Purchasing Document"]]),
            "item": _clean(row[idx["Item"]]),
            "item_description": _clean(row[idx["Item Description"]]) or "",
            "order_unit": _clean(row[idx["Order Unit"]]),
            "order_quantity": row[idx["Order Quantity"]],
        })
    return out


def parse_workbook(blob: bytes, filename: str) -> Dict[str, Any]:
    try:
        wb = openpyxl.load_workbook(BytesIO(blob), data_only=True, read_only=True)
    except Exception as e:
        raise ValueError(f"Could not open '{filename}' as an Excel file: {e}")

    baselines = _read_baselines(wb)
    if not baselines:
        raise ValueError(
            f"'{filename}' has no 'WBS Baseline PSS...' sheets (found: "
            f"{', '.join(wb.sheetnames)}). This needs to be the WBS-for-CPAG-"
            f"automation workbook.")
    dump = _read_dump(wb)
    return {"baselines": baselines, "dump": dump}


def ingest_procurement_wbs(db: Session, blob: bytes, filename: str) -> Dict[str, Any]:
    """Replaces every row of both tables - this upload is a full snapshot,
    the same convention the ZPSPS007 sync uses for mt_poamount."""
    from models import MTZps021, CPAGWbsBaseline

    parsed = parse_workbook(blob, filename)
    now = datetime.utcnow()

    db.query(MTZps021).delete()
    db.query(CPAGWbsBaseline).delete()
    db.bulk_save_objects([
        MTZps021(uploaded_at=now, **row) for row in parsed["dump"]
    ])
    baseline_rows = []
    for pss, pkgs in parsed["baselines"].items():
        for i, pkg in enumerate(pkgs):
            baseline_rows.append(CPAGWbsBaseline(
                pss=pss, package=pkg["package"], wbs_element=pkg["wbs"],
                sort_order=i, uploaded_at=now))
    db.bulk_save_objects(baseline_rows)
    db.commit()

    return {
        "projects": sorted(parsed["baselines"]),
        "packages": sum(len(v) for v in parsed["baselines"].values()),
        "poLines": len(parsed["dump"]),
        "uploadedAt": now.isoformat(),
    }


def _po_rows(lines: List[Dict[str, Any]], main_item_keyword: Optional[str]) -> List[Dict[str, Any]]:
    """One row per Purchasing Document under a WBS - see module docstring."""
    by_po: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for ln in lines:
        if ln["po"]:
            by_po[ln["po"]].append(ln)

    out = []
    for po, po_lines in sorted(by_po.items(), key=lambda kv: kv[1][0]["date"] or ""):
        units = Counter(ln["unit"] for ln in po_lines if ln["unit"])
        mixed = len(units) > 1
        if mixed and main_item_keyword:
            matching = [ln for ln in po_lines if ln["item"].lower().startswith(main_item_keyword)]
        elif mixed:
            matching = []
        else:
            matching = po_lines

        if matching:
            main_unit = matching[0]["unit"]
            qty = sum(float(ln["qty"] or 0) for ln in matching)
            uom, divisor = UOM_MAP.get(main_unit, (main_unit or "-", 1.0))
            qty_out = round(qty / divisor, 1) if divisor != 1 else round(qty)
            uom_out = uom
        else:
            qty_out, uom_out = None, None
        vendor = next((ln["vendor"] for ln in po_lines if ln["vendor"]), None)
        date = next((ln["date"] for ln in po_lines if ln["date"]), None)
        out.append({
            "poNumber": po, "poDate": date, "vendor": vendor,
            "uom": uom_out, "qty": qty_out, "mixedUnresolved": mixed and not matching,
        })
    return out


def procurement_wbs_rows(db: Session) -> Dict[str, List[Dict[str, Any]]]:
    """Every BESS project's Procurement package rows, live from mt_zps021 +
    cpag_wbs_baseline - the CPAG deck's actual read path. Empty (not an
    error) until the first upload."""
    baseline = db.execute(text(
        "select pss, package, wbs_element from cpag_wbs_baseline order by pss, sort_order"
    )).fetchall()
    if not baseline:
        return {}

    dump_rows = db.execute(text(
        "select wbs_element, purchasing_document, vendor_name, order_unit, "
        "order_quantity, item_description, document_date from mt_zps021"
    )).fetchall()
    by_wbs: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for wbs, po, vendor, unit, qty, item, date in dump_rows:
        by_wbs[wbs].append({
            "po": po, "vendor": vendor, "unit": unit, "qty": qty,
            "item": item or "", "date": date.isoformat() if date else None,
        })

    projects: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for pss, package, wbs in baseline:
        keyword = MAIN_ITEM_KEYWORD.get(package)
        for po_row in _po_rows(by_wbs.get(wbs, []), keyword):
            projects[pss].append({"package": package, "wbs": wbs, **po_row})
    return dict(projects)


def procurement_wbs_meta(db: Session) -> Dict[str, Any]:
    row = db.execute(text(
        "select max(uploaded_at), count(distinct pss) from cpag_wbs_baseline")).fetchone()
    return {"uploadedAt": row[0].isoformat() if row and row[0] else None,
            "projectCount": row[1] if row else 0}
