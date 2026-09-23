import os
import sys
import pandas as pd

backend_dir = r"d:\adani\Akasha\backend"
sys.path.insert(0, backend_dir)

from database import SessionLocal
import models
from services.module_wattage import module_watts
from scripts.ingest_sap_data import (
    build_wbs_mapping, match_wbs_to_master, safe_float, safe_sap_id, safe_str,
    _zsps_filters
)

new_file = r"d:\adani\Akasha\Data\19_09\ZPSPS007 4.XLSX"
master_path = r"d:\adani\Akasha\Data\19_09\AKASHA SAP MASTER FILE (1) 1.xlsx"

wbs_map = build_wbs_mapping(master_path)

df = pd.read_excel(new_file)
df = _zsps_filters(df)

db = SessionLocal()

# Load live mt_poamount for matching POs
pos_in_new = df['C.Document'].dropna().astype(str).str.strip().str.replace(r'\.0$', '', regex=True).unique()
print(f"Unique POs in new file after filters: {len(pos_in_new)}")

# Let's inspect each line
records = []
for idx, r in df.iterrows():
    po = safe_sap_id(r.get('C.Document', ''))
    wbs = safe_str(r.get('WBS Element', ''))
    text = safe_str(r.get('Short text', ''))
    c_qty = safe_float(r.get('C.Quantity', 0))
    a_qty = safe_float(r.get('A.Quantity', 0))
    tot_qty = c_qty + a_qty
    c_amt = safe_float(r.get('Commitment Amt', 0))
    a_amt = safe_float(r.get('Actual Amount', 0))
    tot_amt = c_amt + a_amt
    watt = module_watts(text)
    mwp = (tot_qty * watt / 1e6) if watt else 0.0

    records.append({
        'po': po,
        'line': safe_sap_id(r.get('C.Document line', '')) or '',
        'wbs': wbs,
        'text': text,
        'c_qty': c_qty,
        'a_qty': a_qty,
        'tot_qty': tot_qty,
        'c_amt': c_amt,
        'a_amt': a_amt,
        'tot_amt': tot_amt,
        'watt': watt,
        'mwp': mwp
    })

df_parsed = pd.DataFrame(records)

# Fetch live DB rows for these POs
live_rows = db.query(models.MTPOAmount).filter(
    models.MTPOAmount.purchasing_document.in_(list(pos_in_new))
).all()

print(f"Total live rows in DB for these POs: {len(live_rows)}")

# Build lookup by fingerprint: (po, wbs.upper(), text.upper())
# Note: In DB, po_quantities is tot_qty (c_qty + a_qty)
# Let's compare totals per (PO, WBS, Short Text)
live_summary = {}
for r in live_rows:
    key = (str(r.purchasing_document), str(r.wbs_element).upper(), str(r.short_text or '').strip().upper())
    if key not in live_summary:
        live_summary[key] = {
            'qty': 0.0,
            'net_val': 0.0,
            'still_qty': 0.0,
            'del_qty': 0.0,
            'mwp': 0.0,
            'rows': 0
        }
    live_summary[key]['qty'] += (r.po_quantities or 0.0)
    live_summary[key]['net_val'] += (r.net_order_value_inr or 0.0)
    live_summary[key]['still_qty'] += (r.still_to_deliver_qty or 0.0)
    live_summary[key]['del_qty'] += (r.delivered_qty or 0.0)
    live_summary[key]['mwp'] += (r.po_quantities_mw or 0.0)
    live_summary[key]['rows'] += 1

new_summary = {}
for _, r in df_parsed.iterrows():
    key = (str(r['po']), str(r['wbs']).upper(), str(r['text']).strip().upper())
    if key not in new_summary:
        new_summary[key] = {
            'qty': 0.0,
            'net_val': 0.0,
            'c_qty': 0.0,
            'a_qty': 0.0,
            'mwp': 0.0,
            'rows': 0,
            'watt': r['watt']
        }
    new_summary[key]['qty'] += r['tot_qty']
    new_summary[key]['net_val'] += r['tot_amt']
    new_summary[key]['c_qty'] += r['c_qty']
    new_summary[key]['a_qty'] += r['a_qty']
    new_summary[key]['mwp'] += r['mwp']
    new_summary[key]['rows'] += 1

# Compare keys
all_keys = set(live_summary.keys()) | set(new_summary.keys())
keys_only_in_new = set(new_summary.keys()) - set(live_summary.keys())
keys_only_in_live = set(live_summary.keys()) - set(new_summary.keys())
common_keys = set(live_summary.keys()) & set(new_summary.keys())

print(f"\nKeys in new: {len(new_summary)}")
print(f"Keys in live: {len(live_summary)}")
print(f"Common keys: {len(common_keys)}")
print(f"Keys only in new: {len(keys_only_in_new)}")
print(f"Keys only in live: {len(keys_only_in_live)}")

# Check differences in common keys
diffs = []
for k in common_keys:
    n = new_summary[k]
    l = live_summary[k]
    qty_diff = round(n['qty'] - l['qty'], 2)
    val_diff_cr = round((n['net_val'] - l['net_val']) / 1e7, 4)
    mwp_diff = round(n['mwp'] - l['mwp'], 4)
    c_qty_diff = round(n['c_qty'] - l['still_qty'], 2)
    a_qty_diff = round(n['a_qty'] - l['del_qty'], 2)

    if abs(qty_diff) > 0.01 or abs(val_diff_cr) > 0.01 or abs(c_qty_diff) > 0.01 or abs(a_qty_diff) > 0.01:
        diffs.append({
            'po': k[0],
            'wbs': k[1],
            'text': k[2],
            'watt': n['watt'],
            'live_tot_qty': l['qty'],
            'new_tot_qty': n['qty'],
            'qty_diff': qty_diff,
            'live_still_qty': l['still_qty'],
            'new_c_qty': n['c_qty'],
            'c_qty_diff': c_qty_diff,
            'live_del_qty': l['del_qty'],
            'new_a_qty': n['a_qty'],
            'a_qty_diff': a_qty_diff,
            'live_val_cr': l['net_val'] / 1e7,
            'new_val_cr': n['net_val'] / 1e7,
            'val_diff_cr': val_diff_cr,
            'live_mwp': l['mwp'],
            'new_mwp': n['mwp'],
            'mwp_diff': mwp_diff,
        })

print(f"\nItems with differences: {len(diffs)}")

# Let's inspect PO dates from ME2J
print("\n" + "=" * 80)
print("PO DATES FROM ME2J (mt_me2j_po):")
print("=" * 80)
po_dates = db.query(models.MTME2JPO).filter(models.MTME2JPO.purchasing_document.in_(list(pos_in_new))).all()
date_map = {p.purchasing_document: (p.document_date, p.po_latest_release, p.vendor_name) for p in po_dates}

print(f"Found {len(po_dates)} PO date records in ME2J.")

# Print details of differences
df_diff = pd.DataFrame(diffs)
if not df_diff.empty:
    print("\nSUMMARY OF DIFFERENCES:")
    print(f"Total Net Qty Diff (pieces): {df_diff['qty_diff'].sum():,.0f}")
    print(f"Total Net MWp Diff:         {df_diff['mwp_diff'].sum():,.2f} MWp")
    print(f"Total Net Value Diff (Cr):  Rs {df_diff['val_diff_cr'].sum():,.2f} Cr")
    print(f"Total Delivered Qty Diff:   {df_diff['a_qty_diff'].sum():,.0f} pieces")
    print(f"Total Pending Qty Diff:     {df_diff['c_qty_diff'].sum():,.0f} pieces")
    
    print("\nBreakdown by PO:")
    po_group = df_diff.groupby('po').agg({
        'qty_diff': 'sum',
        'mwp_diff': 'sum',
        'val_diff_cr': 'sum',
        'a_qty_diff': 'sum',
        'c_qty_diff': 'sum',
    }).reset_index()
    for _, row in po_group.iterrows():
        p = row['po']
        dt_info = date_map.get(p, (None, None, 'Unknown Vendor'))
        print(f"  PO {p} (Vendor: {dt_info[2]}, Doc Date: {dt_info[0]}, Latest Release: {dt_info[1]}):")
        print(f"    Total Qty Diff: {row['qty_diff']:+,.0f} pcs | MWp Diff: {row['mwp_diff']:+,.2f} MWp | Value Diff: Rs {row['val_diff_cr']:+,.2f} Cr")
        print(f"    Delivered (A.Qty) Diff: {row['a_qty_diff']:+,.0f} pcs | Pending (C.Qty) Diff: {row['c_qty_diff']:+,.0f} pcs")
else:
    print("NO DIFFERENCES at aggregated PO/WBS/text level!")

db.close()
