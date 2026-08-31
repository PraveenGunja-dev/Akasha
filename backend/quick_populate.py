import sys; sys.path.append('backend')
from dotenv import load_dotenv; load_dotenv('backend/.env')
import pandas as pd
from database import SessionLocal
import models
import os
from scripts.ingest_sap_data import safe_sap_id, safe_str

db = SessionLocal()

print("Clearing lookup...")
db.query(models.MTEInvoicePOLookup).delete()
db.commit()

data_dir = os.path.join("Data", "NEW31")
zsps_path = os.path.join(data_dir, "ZPSPS007 (3).xlsx")
me2j_path = os.path.join(data_dir, "Me2J 1.xlsx")

lookup_records = {}

print("Reading ME2J...")
if os.path.exists(me2j_path):
    df_me2j = pd.read_excel(me2j_path, usecols=['Purchasing Document', 'WBS Element'])
    for _, row in df_me2j.iterrows():
        po = safe_sap_id(row.get('Purchasing Document', ''))
        wbs = safe_str(row.get('WBS Element', ''))
        if po and wbs and wbs.lower() not in ('nan', 'none'):
            lookup_records[po] = wbs

print("Reading ZSPS...")
if os.path.exists(zsps_path):
    df_zsps = pd.read_excel(zsps_path, usecols=['C.Document', 'WBS Element'])
    for _, row in df_zsps.iterrows():
        po = safe_sap_id(row.get('C.Document', ''))
        wbs = safe_str(row.get('WBS Element', ''))
        if po and wbs and wbs.lower() not in ('nan', 'none'):
            lookup_records[po] = wbs

inserts = [models.MTEInvoicePOLookup(purchasing_document=po, wbs_element=wbs) for po, wbs in lookup_records.items()]
BATCH = 5000
for i in range(0, len(inserts), BATCH):
    db.add_all(inserts[i:i+BATCH])
    db.commit()

print(f"Inserted {len(inserts)} records into E-Invoice PO Lookup!")
