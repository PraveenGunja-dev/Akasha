import os
import sys
import pandas as pd

backend_dir = r"d:\adani\Akasha\backend"
sys.path.insert(0, backend_dir)

from database import SessionLocal
import models
from scripts.ingest_sap_data import safe_sap_id, safe_float, safe_str, _zsps_filters

new_file = r"d:\adani\Akasha\Data\19_09\ZPSPS007 4.XLSX"
df = pd.read_excel(new_file)
df = _zsps_filters(df)

# Group by PO in new file
df['tot_qty'] = df['C.Quantity'].fillna(0) + df['A.Quantity'].fillna(0)
new_po_summary = df.groupby('C.Document').agg({
    'C.Quantity': 'sum',
    'A.Quantity': 'sum',
    'tot_qty': 'sum',
    'Short text': lambda s: list(set(s.dropna()))[0] if len(s.dropna()) > 0 else '',
    'Vendor Name': lambda s: list(set(s.dropna()))[0] if len(s.dropna()) > 0 else ''
}).reset_index()

db = SessionLocal()

results = []
for _, r in new_po_summary.iterrows():
    po = safe_sap_id(r['C.Document'])
    new_tot = r['tot_qty']
    new_c = r['C.Quantity']
    new_a = r['A.Quantity']
    
    # Live DB
    live_rows = db.query(models.MTPOAmount).filter(models.MTPOAmount.purchasing_document == po).all()
    live_tot = sum(row.po_quantities or 0 for row in live_rows)
    live_c = sum(row.still_to_deliver_qty or 0 for row in live_rows)
    live_a = sum(row.delivered_qty or 0 for row in live_rows)
    
    # ME2J vendor if available
    me2j_po = db.query(models.MTME2JPO).filter(models.MTME2JPO.purchasing_document == po).first()
    vendor = me2j_po.vendor_name if me2j_po and me2j_po.vendor_name else r['Vendor Name']
    doc_date = str(me2j_po.document_date).split(' ')[0] if me2j_po and me2j_po.document_date else ''
    
    diff = new_tot - live_tot
    results.append({
        'po': po,
        'vendor': vendor,
        'doc_date': doc_date,
        'live_tot': live_tot,
        'new_tot': new_tot,
        'diff': diff,
        'live_c': live_c,
        'new_c': new_c,
        'live_a': live_a,
        'new_a': new_a,
        'match': 'MATCH' if abs(diff) < 0.01 and abs(new_c - live_c) < 0.01 and abs(new_a - live_a) < 0.01 else ('REBALANCED' if abs(diff) < 0.01 else 'DIFF')
    })

db.close()

df_res = pd.DataFrame(results).sort_values('po')
print(f"Total POs checked: {len(df_res)}")
print(f"Matches count: {(df_res['match'] == 'MATCH').sum()}")
print(f"Differences count: {(df_res['match'] != 'MATCH').sum()}")

print("\nAll 49 POs:")
for _, r in df_res.iterrows():
    print(f"PO {r['po']} | Date: {r['doc_date']:10} | Live Qty: {r['live_tot']:10,.0f} | New Qty: {r['new_tot']:10,.0f} | Diff: {r['diff']:+8,.0f} | Status: {r['match']} | Vendor: {r['vendor']}")
