"""Ariba ZIBDSESREP -> ariba_inbound_delivery, and the mapping of its lines to WBS.

ZIBDSESREP is the inbound-delivery (IBD) / service-entry-sheet (SES) report.
One row per delivery event against a PO line: the IBD (dispatch) date, the GR
posting date and quantity (received at site) and the finance checklist raised
on receipt. Facts checked against the 2026-10-08 extract (76,222 rows):

- The 6 rows with no PO number are Excel total rows (PO qty up to 1.1e9).
- Rows with no IBD creation date are service entry sheets (UoM 'LE', no
  material number, "Consultancy Services"). They are not deliveries and are
  not loaded.
- 2,740 rows are exact copies. Dropping them takes Ariba GRN vs SAP delivered
  from 8.5% to 83% agreement on the PO lines that carry them, so they are
  duplicates of one event, not two events.
- PO Quantity repeats on every row of a line. Never sum it.
- GRN quantity is per receipt and DOES sum: per (PO, item) it agrees with the
  CO Actual GR quantity on 99.5% of 13,999 lines.
- IBD quantity does NOT sum. A shipment received in two lots appears as two
  rows, each repeating the full IBD quantity (14,400) beside its own GRN
  (6,480 / 7,920). Subtracting per row reports the whole shipment as still in
  transit. The extract carries no IBD or GRN document number, so the lots
  cannot be regrouped: "awaiting GRN" is therefore taken only from rows with
  no GR posting date, which is a lower bound.
- Checklist Status is only ever 'CREATED' or blank; blank means none raised.

Ariba carries only the PO number and item. Its WBS (and so its project) comes
from the SAP CO line of the same (PO, item) - never from the PO alone: 828 CO
POs span several WBS elements, 216 of them with Ariba deliveries.

    cd backend && ./venv/Scripts/python.exe -m services.ariba_service [path]
"""
import glob
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ARIBA_FILE_PATTERN = re.compile(r"^ZIBDSESREP.*\.xlsx?$", re.I)
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Newest file wins: the SAP download folder SharePoint lands files in, then
# Data/ARIBA where the first extract was dropped by hand.
SEARCH_DIRS = [os.path.join(_REPO, "Data", "19_09"), os.path.join(_REPO, "Data", "ARIBA")]

# Extract header -> column. Matched exactly (case/space-insensitive): a
# substring match let 'Item' claim other headers.
COLUMNS = {
    "po number": "po_number",
    "item": "item",
    "material number": "material_number",
    "material description": "material_description",
    "po quantity": "po_quantity",
    "uom": "uom",
    "company code": "company_code",
    "vendor code": "vendor_code",
    "vendor name": "vendor_name",
    "inbound delivery quantity": "inbound_delivery_quantity",
    "rejected quantity": "rejected_quantity",
    "ibd creation date": "ibd_creation_date",
    "plant": "plant",
    "gr posting date": "gr_posting_date",
    "grn quantity": "grn_quantity",
    "currency": "currency",
    "ariba invoice date": "ariba_invoice_date",
    "checklist number": "checklist_number",
    "checklist status": "checklist_status",
    "checklist_date": "checklist_date",
    "checklist date": "checklist_date",
}
CODE_COLS = ("po_number", "item", "material_number", "company_code", "vendor_code", "plant", "checklist_number")
TEXT_COLS = ("material_description", "uom", "vendor_name", "currency", "checklist_status")
QTY_COLS = ("po_quantity", "inbound_delivery_quantity", "rejected_quantity", "grn_quantity")
DATE_COLS = ("ibd_creation_date", "gr_posting_date", "ariba_invoice_date", "checklist_date")


def find_ariba_file() -> Optional[str]:
    found = [p for d in SEARCH_DIRS for p in glob.glob(os.path.join(d, "*"))
             if ARIBA_FILE_PATTERN.match(os.path.basename(p)) and not os.path.basename(p).startswith("~$")]
    return max(found, key=os.path.getmtime) if found else None


def _code(v) -> Optional[str]:
    """Excel hands numeric codes back as floats (4510013104.0); store '4510013104'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s or None


def _text(v) -> Optional[str]:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return s if s and s.lower() != "nan" else None


def _qty(v) -> float:
    try:
        f = float(v)
        return 0.0 if pd.isna(f) else f
    except (TypeError, ValueError):
        return 0.0


def _date(v) -> Optional[datetime]:
    if v is None or pd.isna(v):
        return None
    try:
        return pd.Timestamp(v).to_pydatetime()
    except (TypeError, ValueError):
        return None


def sync_ariba_inbound_deliveries(db: Session, excel_path: Optional[str] = None) -> dict:
    """Replace ariba_inbound_delivery with the material IBD lines of the extract.

    The report is a full snapshot, so the table is replaced in one transaction;
    a file that yields no delivery rows is refused and the previous load kept."""
    from models import AribaInboundDelivery

    path = excel_path or find_ariba_file()
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"No ZIBDSESREP extract in {SEARCH_DIRS}")

    df = pd.read_excel(path)
    df = df.rename(columns={c: COLUMNS[k] for c in df.columns
                            if (k := re.sub(r"\s+", " ", str(c)).strip().lower()) in COLUMNS})
    missing = [c for c in ("po_number", "item", "inbound_delivery_quantity", "ibd_creation_date", "grn_quantity")
               if c not in df.columns]
    if missing:
        raise ValueError(f"ZIBDSESREP is missing expected columns: {missing}")

    raw = len(df)
    total_rows = int(df["po_number"].isna().sum())
    df = df[df["po_number"].notna()]
    service_rows = int(df["ibd_creation_date"].isna().sum())
    df = df[df["ibd_creation_date"].notna()]
    dup_rows = int(df.duplicated().sum())
    df = df.drop_duplicates()

    records = []
    for r in df.to_dict("records"):
        rec = {c: _code(r.get(c)) for c in CODE_COLS}
        rec.update({c: _text(r.get(c)) for c in TEXT_COLS})
        rec.update({c: _qty(r.get(c)) for c in QTY_COLS})
        rec.update({c: _date(r.get(c)) for c in DATE_COLS})
        if rec["checklist_number"] is None:
            rec["checklist_status"] = None
        records.append(rec)
    if not records:
        raise RuntimeError(f"{os.path.basename(path)} has no inbound-delivery rows - previous Ariba load kept")

    now = datetime.utcnow()
    for rec in records:
        rec["uploaded_at"] = now
    try:
        db.query(AribaInboundDelivery).delete()
        for i in range(0, len(records), 5000):
            db.bulk_insert_mappings(AribaInboundDelivery, records[i:i + 5000])
        db.commit()
    except Exception:
        db.rollback()
        raise

    summary = {"file": os.path.basename(path), "rows_in_file": raw, "loaded": len(records),
               "total_rows_skipped": total_rows, "service_rows_skipped": service_rows,
               "duplicate_rows_skipped": dup_rows,
               "pos": len({r["po_number"] for r in records})}
    logger.info(f"Ariba IBD load: {summary}")
    return summary


# ── Mapping to WBS ───────────────────────────────────────────────────────────

def _f(v) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def load_ariba_allocations(db: Session, po_numbers: Optional[set] = None) -> dict:
    """Every Ariba delivery row, with the WBS element(s) its PO line belongs to.

    Returns {"rows": [...], "unmapped_lines": n}. Each row carries
    `allocations`: [(wbs_element, share)], shares summing to 1. The WBS comes
    from the SAP CO lines of the same (PO, item); a line booked to several WBS
    is split by CO quantity. A line missing from CO falls back to the PO's WBS
    in mt_poamount only when the whole PO sits on ONE WBS - otherwise the row
    stays unmapped rather than being credited to a guessed project.

    `is_module` / `mw_per_unit` come from the CO material text (the same
    PANEL rule and wattage parser the PO tables use), so MWp is computed
    exactly as SAP's ordered MWp is."""
    from services.module_wattage import mw_factor

    params, where = {}, ""
    if po_numbers is not None:
        if not po_numbers:
            return {"rows": [], "unmapped_lines": 0}
        params["pos"] = list(po_numbers)
        where = "where po_number = any(:pos)"
    rows = [dict(r) for r in db.execute(text(f"""
        select po_number, item, material_number, material_description, uom, vendor_code, vendor_name,
               plant, inbound_delivery_quantity, rejected_quantity, grn_quantity,
               ibd_creation_date, gr_posting_date, checklist_number, checklist_status, checklist_date
        from ariba_inbound_delivery {where}"""), params).mappings()]
    if not rows:
        return {"rows": [], "unmapped_lines": 0}

    pos = list({r["po_number"] for r in rows})
    co = db.execute(text("""
        select po_document, po_item, wbs_element, sum(abs(coalesce(quantity, 0))),
               bool_or(is_module), max(material_description)
        from sap_co_line
        where po_document = any(:pos) and po_item is not null and wbs_element is not null
        group by 1, 2, 3"""), {"pos": pos}).fetchall()
    by_line: dict[tuple, list] = defaultdict(list)
    line_meta: dict[tuple, dict] = {}
    for po, item, wbs, qty, is_mod, mdesc in co:
        key = (str(po).strip(), str(item).strip().lstrip("0"))
        by_line[key].append((wbs, _f(qty)))
        meta = line_meta.setdefault(key, {"is_module": False, "mw": None})
        meta["is_module"] = meta["is_module"] or bool(is_mod)
        meta["mw"] = meta["mw"] or (mw_factor(mdesc or "") if is_mod else None)

    po_wbs: dict[str, set] = defaultdict(set)
    po_mw: dict[str, float] = {}
    for po, wbs, mw in db.execute(text("""
            select purchasing_document, wbs_element, max(mw_multiplication_factor)
            from mt_poamount where purchasing_document = any(:pos) and wbs_element is not null
            group by 1, 2"""), {"pos": pos}):
        po_wbs[str(po).strip()].add(wbs)
        if mw:
            po_mw[str(po).strip()] = float(mw)

    unmapped = set()
    for r in rows:
        key = (r["po_number"], str(r["item"] or "").lstrip("0"))
        lines = by_line.get(key)
        if lines:
            total = sum(q for _, q in lines)
            r["allocations"] = [(w, (q / total) if total > 0 else 1 / len(lines)) for w, q in lines]
            r["mapped_by"] = "po_item"
        elif len(po_wbs.get(r["po_number"], ())) == 1:
            r["allocations"] = [(next(iter(po_wbs[r["po_number"]])), 1.0)]
            r["mapped_by"] = "po"
        else:
            r["allocations"] = []
            r["mapped_by"] = None
            unmapped.add(key)
        meta = line_meta.get(key, {})
        r["is_module"] = bool(meta.get("is_module"))
        r["mw_per_unit"] = meta.get("mw") or mw_factor(r["material_description"] or "") or (
            po_mw.get(r["po_number"]) if r["is_module"] else None)
    return {"rows": rows, "unmapped_lines": len(unmapped)}


def delivery_events(rows: list, share_by_wbs) -> list:
    """Group allocated Ariba rows into delivery events for one project.

    One event per (PO, dispatch date, receipt date): rows on the same PO that
    left and landed on the same days are one consignment for planning; any
    difference in either date is a separate event, never merged.

    share_by_wbs(wbs) -> this project's share of that WBS element (0 when the
    WBS is not the project's). Quantities are the received GRN for received
    rows and the dispatched IBD quantity for rows awaiting GRN."""
    today = datetime.utcnow().date()
    events: dict[tuple, dict] = {}
    for r in rows:
        share = sum(s * share_by_wbs(w) for w, s in r["allocations"])
        if share <= 0:
            continue
        ibd_dt, gr_dt = r["ibd_creation_date"], r["gr_posting_date"]
        received = gr_dt is not None
        qty = (_f(r["grn_quantity"]) if received else _f(r["inbound_delivery_quantity"])) * share
        key = (r["po_number"], ibd_dt.date() if ibd_dt else None, gr_dt.date() if gr_dt else None)
        e = events.get(key)
        if e is None:
            e = events[key] = {
                "po": r["po_number"], "vendor": r["vendor_name"] or "",
                "dispatch_date": key[1].isoformat() if key[1] else None,
                "receipt_date": key[2].isoformat() if key[2] else None,
                "transit_days": (key[2] - key[1]).days if key[1] and key[2] else None,
                "age_days": (today - key[1]).days if key[1] and not received else None,
                "status": "received" if received else "awaiting_grn",
                "qty": 0.0, "mwp": 0.0, "mwp_known": True, "rejected_qty": 0.0,
                "uom": r["uom"] or "", "rows": 0, "checklist_created": 0,
                "checklist_numbers": [], "checklist_date": None, "share": share,
                "lines": set(),
            }
        e["qty"] += qty
        if r["mw_per_unit"]:
            e["mwp"] += qty * r["mw_per_unit"]
        else:
            e["mwp_known"] = False
        e["rejected_qty"] += _f(r["rejected_quantity"]) * share
        e["rows"] += 1
        e["lines"].add(str(r["item"] or ""))
        e["share"] = min(e["share"], share)
        if r["checklist_number"]:
            e["checklist_created"] += 1
            if r["checklist_number"] not in e["checklist_numbers"]:
                e["checklist_numbers"].append(r["checklist_number"])
            cd = r["checklist_date"].date().isoformat() if r["checklist_date"] else None
            if cd and (e["checklist_date"] is None or cd > e["checklist_date"]):
                e["checklist_date"] = cd
    out = []
    for e in events.values():
        e["qty"] = round(e["qty"], 2)
        e["mwp"] = round(e["mwp"], 3)
        e["rejected_qty"] = round(e["rejected_qty"], 2)
        e["lines"] = sorted(e["lines"], key=lambda s: (len(s), s))
        e["share"] = round(e["share"], 4)
        out.append(e)
    out.sort(key=lambda e: (e["dispatch_date"] or "", e["receipt_date"] or "9999", e["po"]))
    return out


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    logging.basicConfig(level=logging.INFO)
    from database import SessionLocal
    _db = SessionLocal()
    try:
        print(sync_ariba_inbound_deliveries(_db, sys.argv[1] if len(sys.argv) > 1 else None))
    finally:
        _db.close()
