import os
import sys
import pandas as pd

backend_dir = r"d:\adani\Akasha\backend"
sys.path.insert(0, backend_dir)

from database import SessionLocal
import models
from scripts.ingest_sap_data import _zsps_filters

new_file = r"d:\adani\Akasha\Data\19_09\ZPSPS007 4.XLSX"
df = pd.read_excel(new_file)
df = _zsps_filters(df)

pos = df['C.Document'].dropna().astype(str).str.strip().str.replace(r'\.0$', '', regex=True).unique()

db = SessionLocal()
me2j_records = db.query(models.MTME2JPO).filter(models.MTME2JPO.purchasing_document.in_(list(pos))).all()

rows = []
for r in me2j_records:
    rows.append({
        'PO': r.purchasing_document,
        'Vendor': r.vendor_name,
        'Doc_Date': r.document_date,
        'Latest_Release_Date': r.po_latest_release,
        'First_Release_Date': r.po_first_release,
        'Amendment_No': r.amendment_no,
        'Amendment_Date': r.amendment_date
    })

df_dates = pd.DataFrame(rows)
print(f"Total POs: {len(pos)}, POs found in ME2J: {len(df_dates)}")
print("\nDocument Date Range:")
print(f"Earliest PO Date: {df_dates['Doc_Date'].min()}")
print(f"Latest PO Date:   {df_dates['Doc_Date'].max()}")

print("\nLatest Release Date Range:")
print(f"Earliest Release: {df_dates['Latest_Release_Date'].min()}")
print(f"Latest Release:   {df_dates['Latest_Release_Date'].max()}")

print("\nSample PO Dates:")
print(df_dates[['PO', 'Vendor', 'Doc_Date', 'Latest_Release_Date', 'Amendment_No', 'Amendment_Date']].head(10).to_string())

db.close()
