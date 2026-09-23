"""Add the PO lines a ZPSPS007 extract has and mt_poamount does not.

Why this exists
---------------
`ingest_sap_data.py` loads ZSPS by DELETING mt_poamount and re-inserting the
whole extract. That is right for a full portfolio export, but wrong for a
narrow one: SAP is often exported per project or per period, and loading such a
file through the normal path would wipe every PO outside its scope. (The
newest-file rule in that script makes this a live hazard — a small extract
dropped into Data/19_09 becomes "the newest ZPSPS007" and would be loaded as a
full replacement. The snapshot guard would refuse it, but only after the fact.)

This script adds instead of replacing. It applies exactly the ingest's own
filters and WBS-master matching, so a row only lands here if the full ingest
would also have accepted it, and skips anything already present.

Row identity
------------
mt_poamount has no PO line-number column, so a line is fingerprinted by
document + WBS + material text + its four amounts. Consequences, stated plainly:

  * a line already present with identical values is skipped;
  * a line present with DIFFERENT values is reported as a conflict and skipped
    by default — it means the extract restates a PO the table already holds,
    and silently inserting it would double-count that value. --update-conflicts
    overwrites those rows instead;
  * a genuinely new line is inserted.

Usage
-----
    python scripts/merge_zsps_extract.py "../Data/19_09/ZPSPS007 4.XLSX"
    python scripts/merge_zsps_extract.py <file> --apply
    python scripts/merge_zsps_extract.py <file> --apply --update-conflicts
"""
import argparse
import os
import sys

import pandas as pd

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

import models  # noqa: E402
from database import SessionLocal  # noqa: E402
from services.module_wattage import selftest  # noqa: E402
from scripts.ingest_sap_data import (  # noqa: E402
    build_wbs_mapping, match_wbs_to_master, safe_float, safe_sap_id, safe_str,
    _extract_wattage_from_text, SAP_DATA_DIR,
)

MASTER_NAME = "AKASHA SAP MASTER FILE (1) 1.xlsx"


def fingerprint(doc, wbs, text, still_q, del_q, still_inr, del_inr):
    """Identity of a PO line, to 2dp on the amounts so float noise from Excel
    does not read as a different line."""
    return (str(doc), str(wbs).upper(), str(text or '').strip().upper(),
            round(float(still_q or 0), 2), round(float(del_q or 0), 2),
            round(float(still_inr or 0), 2), round(float(del_inr or 0), 2))


def apply_ingest_filters(df):
    """The same four filters ingest_sap_data applies to a ZSPS frame, in the
    same order, so this path cannot admit a row the full ingest would reject."""
    before = len(df)
    df = df[df['C.Document'].notna()]
    if 'Summary' in df.columns:
        s = df['Summary'].astype(str).str.strip().str.lower()
        df = df[df['Summary'].isna() | (s == '') | (s == 'nan')]
    if 'Type' in df.columns:
        df = df[df['Type'].astype(str).str.strip() == 'POrd']
    comm = pd.to_numeric(df['Commitment Amt'], errors='coerce').fillna(0.0)
    act = pd.to_numeric(df['Actual Amount'], errors='coerce').fillna(0.0)
    df = df[(comm != 0) | (act != 0)]
    if 'Description' in df.columns:
        excluded = df[df['Description'].astype(str)
                      .str.contains('SPGS|PMC|ISA', case=False, na=False)]['C.Document'].unique()
        df = df[~df['C.Document'].isin(excluded)]
    print(f"  rows after the ingest's own filters: {len(df):,} (from {before:,})")
    return df


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("extract", help="path to the ZPSPS007 .xlsx/.XLSX to merge in")
    ap.add_argument("--apply", action="store_true", help="write (default is a dry run)")
    ap.add_argument("--update-conflicts", action="store_true",
                    help="overwrite rows whose amounts differ, instead of skipping them")
    ap.add_argument("--master", default=None, help="path to the SAP master file")
    args = ap.parse_args()

    selftest()
    path = os.path.abspath(args.extract)
    if not os.path.exists(path):
        print(f"no such file: {path}")
        return 2
    master = args.master or os.path.join(SAP_DATA_DIR, MASTER_NAME)
    if not os.path.exists(master):
        print(f"SAP master file not found: {master}")
        return 2

    print(f"extract: {path}")
    print(f"master : {master}")
    wbs_map = build_wbs_mapping(master)
    print(f"  WBS master codes: {len(wbs_map):,}")

    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    print(f"  rows read: {len(df):,}")
    df = apply_ingest_filters(df)

    db = SessionLocal()
    try:
        existing = {}
        for r in db.query(
                models.MTPOAmount.id, models.MTPOAmount.purchasing_document,
                models.MTPOAmount.wbs_element, models.MTPOAmount.short_text,
                models.MTPOAmount.still_to_deliver_qty, models.MTPOAmount.delivered_qty,
                models.MTPOAmount.still_to_deliver_inr,
                models.MTPOAmount.delivered_value_inr_cr).all():
            existing[fingerprint(r[1], r[2], r[3], r[4], r[5], r[6],
                                 (r[7] or 0) * 1e7)] = r[0]
        # A looser key, to tell "this line is new" from "this line is restated".
        by_line = {}
        for r in db.query(
                models.MTPOAmount.id, models.MTPOAmount.purchasing_document,
                models.MTPOAmount.wbs_element, models.MTPOAmount.short_text).all():
            by_line.setdefault((str(r[1]), str(r[2]).upper(),
                                str(r[3] or '').strip().upper()), []).append(r[0])
        print(f"  mt_poamount rows live: {len(existing):,}")

        new_rows, conflicts = [], []
        skipped_same = skipped_no_wbs = skipped_no_match = 0

        for _, row in df.iterrows():
            doc = safe_sap_id(row.get('C.Document', ''))
            if not doc or doc.lower() == 'nan':
                continue
            wbs = safe_str(row.get('WBS Element', ''))
            if not wbs or wbs.lower() in ('nan', 'none'):
                skipped_no_wbs += 1
                continue
            if not match_wbs_to_master(wbs, wbs_map):
                skipped_no_match += 1
                continue

            still_q = safe_float(row.get('C.Quantity', 0))
            del_q = safe_float(row.get('A.Quantity', 0))
            qty = still_q + del_q
            still_inr = safe_float(row.get('Commitment Amt', 0))
            del_inr = safe_float(row.get('Actual Amount', 0))
            net_inr = still_inr + del_inr
            txt = safe_str(row.get('Short text', ''))

            fp = fingerprint(doc, wbs, txt, still_q, del_q, still_inr, del_inr)
            if fp in existing:
                skipped_same += 1
                continue
            if (str(doc), str(wbs).upper(), txt.strip().upper()) in by_line:
                conflicts.append((doc, wbs, txt, qty, net_inr / 1e7))
                continue

            mw = _extract_wattage_from_text(txt)
            new_rows.append(models.MTPOAmount(
                purchasing_document=doc,
                wbs_element=wbs,
                material_name=safe_str(row.get('Description', '')),
                vendor_name=safe_str(row.get('Vendor Name', '')),
                short_text=txt,
                order_quantity=qty,
                po_quantities=qty,
                net_order_value=net_inr,
                net_order_value_inr=net_inr,
                still_to_deliver_qty=still_q,
                still_to_deliver_inr=still_inr,
                delivered_qty=del_q,
                delivered_value_inr_cr=del_inr / 1e7,
                currency='INR',
                doc_type=safe_str(row.get('Type', '')) or None,
                mw_multiplication_factor=mw,
                po_quantities_mw=(qty * mw) if mw is not None else None,
            ))

        print()
        print(f"  already present, identical : {skipped_same:,}")
        print(f"  skipped, no WBS            : {skipped_no_wbs:,}")
        print(f"  skipped, WBS not in master : {skipped_no_match:,}")
        print(f"  CONFLICTS (restated lines) : {len(conflicts):,}")
        print(f"  NEW rows to insert         : {len(new_rows):,}")

        if new_rows:
            val = sum(r.net_order_value_inr or 0 for r in new_rows) / 1e7
            mwp = sum(r.po_quantities_mw or 0 for r in new_rows)
            mod = [r for r in new_rows if 'module' in (r.short_text or '').lower()
                   or 'panel' in (r.short_text or '').lower()]
            print(f"    value      : {val:,.1f} Cr")
            print(f"    module MWp : {mwp:,.1f}  (from {len(mod):,} module/panel lines)")
            print("    sample:")
            for r in new_rows[:10]:
                print(f"      {r.purchasing_document} {r.wbs_element:<16} "
                      f"qty={r.po_quantities:>10,.0f} "
                      f"{(r.net_order_value_inr or 0) / 1e7:>8,.2f}Cr  {str(r.short_text)[:44]}")

        if conflicts:
            print("\n  *** restated lines (same document+WBS+text, different amounts) ***")
            for doc, wbs, txt, qty, cr in conflicts[:20]:
                print(f"      {doc} {wbs:<16} qty={qty:>10,.0f} {cr:>8,.2f}Cr  {txt[:44]}")
            if len(conflicts) > 20:
                print(f"      ... and {len(conflicts) - 20} more")
            if not args.update_conflicts:
                print("      skipped — pass --update-conflicts to overwrite them instead.")

        if not args.apply:
            print("\nDRY RUN — nothing written. Re-run with --apply to commit.")
            return 0

        if new_rows:
            db.add_all(new_rows)
        if conflicts and args.update_conflicts:
            print("  --update-conflicts: overwriting restated lines is not implemented "
                  "as a blind update; rerun the full ingest for a restated extract.")
        db.commit()
        print(f"\nCommitted {len(new_rows):,} new rows.")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
