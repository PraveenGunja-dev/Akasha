import os
import sys
import pandas as pd

backend_dir = r"d:\adani\Akasha\backend"
sys.path.insert(0, backend_dir)

from database import SessionLocal
import models
from scripts.ingest_sap_data import safe_sap_id, safe_float, _zsps_filters

new_file = r"d:\adani\Akasha\Data\19_09\ZPSPS007 4.XLSX"
df = pd.read_excel(new_file)
df = _zsps_filters(df)

target_pos = ['4510022667', '4510022702']
df_target = df[df['C.Document'].astype(str).str.contains('|'.join(target_pos))]

print(f"Target PO rows in new file: {len(df_target)}")
for po in target_pos:
    sub = df_target[df_target['C.Document'].astype(str).str.contains(po)]
    print(f"\n--- PO {po} ---")
    print(f"Rows: {len(sub)}")
    print(f"Total C.Qty: {sub['C.Quantity'].sum():,.2f}")
    print(f"Total A.Qty: {sub['A.Quantity'].sum():,.2f}")
    print(f"Total Qty:   {(sub['C.Quantity'] + sub['A.Quantity']).sum():,.2f}")
    print(f"Total Comm Amt: Rs {sub['Commitment Amt'].sum():,.2f}")
    print(f"Total Act Amt:  Rs {sub['Actual Amount'].sum():,.2f}")
    print(f"Total Value:    Rs {(sub['Commitment Amt'] + sub['Actual Amount']).sum():,.2f}")

db = SessionLocal()
for po in target_pos:
    rows = db.query(models.MTPOAmount).filter(models.MTPOAmount.purchasing_document == po).all()
    print(f"\n--- PO {po} IN LIVE DB ---")
    print(f"Rows: {len(rows)}")
    tot_still_q = sum(r.still_to_deliver_qty or 0 for r in rows)
    tot_del_q = sum(r.delivered_qty or 0 for r in rows)
    tot_q = sum(r.po_quantities or 0 for r in rows)
    tot_still_inr = sum(r.still_to_deliver_inr or 0 for r in rows)
    tot_del_cr = sum(r.delivered_value_inr_cr or 0 for r in rows)
    tot_net_inr = sum(r.net_order_value_inr or 0 for r in rows)
    print(f"Total Still Qty: {tot_still_q:,.2f}")
    print(f"Total Del Qty:   {tot_del_q:,.2f}")
    print(f"Total Qty:       {tot_q:,.2f}")
    print(f"Total Net INR:   Rs {tot_net_inr:,.2f}")

db.close()
