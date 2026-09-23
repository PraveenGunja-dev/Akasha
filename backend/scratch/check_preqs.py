import os
import sys
import pandas as pd

backend_dir = r"d:\adani\Akasha\backend"
sys.path.insert(0, backend_dir)

from database import SessionLocal
import models
from services.module_wattage import module_watts
from scripts.ingest_sap_data import (
    build_wbs_mapping, match_wbs_to_master, safe_float, safe_sap_id, safe_str
)

new_file = r"d:\adani\Akasha\Data\19_09\ZPSPS007 4.XLSX"
old_file = r"d:\adani\Akasha\Data\19_09\ZPSPS007.xlsx"
master_path = r"d:\adani\Akasha\Data\19_09\AKASHA SAP MASTER FILE (1) 1.xlsx"

wbs_map = build_wbs_mapping(master_path)

print("=" * 80)
print("1. CHECKING PREQ (PURCHASE REQUISITIONS) IN NEW FILE (ZPSPS007 4.XLSX)")
print("=" * 80)
df_new = pd.read_excel(new_file)
print(f"Total rows in new file: {len(df_new)}")
print("Types in new file:", df_new['Type'].value_counts(dropna=False).to_dict())

preqs_new = df_new[df_new['Type'].astype(str).str.strip() == 'PReq']
print(f"Number of PReq rows in new file: {len(preqs_new)}")
if not preqs_new.empty:
    print(preqs_new[['C.Document', 'WBS Element', 'Short text', 'C.Quantity', 'Commitment Amt']].head(10))

print("\n" + "=" * 80)
print("2. CHECKING PREQ (PURCHASE REQUISITIONS) IN OLD FILE (ZPSPS007.xlsx)")
print("=" * 80)
# We can read chunk or read relevant columns
df_old_types = pd.read_excel(old_file, usecols=['Type', 'C.Document', 'WBS Element', 'Short text', 'C.Quantity', 'Commitment Amt', 'Description'])
print("Types in old file:", df_old_types['Type'].value_counts(dropna=False).to_dict())

preqs_old = df_old_types[df_old_types['Type'].astype(str).str.strip() == 'PReq']
print(f"Total PReq rows in old file: {len(preqs_old)}")

# Filter for module PReqs in old file
module_preqs = []
for idx, r in preqs_old.iterrows():
    st = str(r.get('Short text', ''))
    desc = str(r.get('Description', ''))
    w = module_watts(st)
    if w or 'module' in st.lower() or 'panel' in st.lower() or 'solar' in st.lower() or 'module' in desc.lower():
        module_preqs.append(r)

df_mod_preqs = pd.DataFrame(module_preqs)
print(f"\nModule-related PReq rows in old file: {len(df_mod_preqs)}")
if not df_mod_preqs.empty:
    print(df_mod_preqs[['C.Document', 'WBS Element', 'Short text', 'C.Quantity', 'Commitment Amt']].to_string())

print("\n" + "=" * 80)
print("3. CHECKING DATABASE mt_slr_data FOR PREQs")
print("=" * 80)
db = SessionLocal()
slr_preqs = db.query(models.MTSLRData).filter(models.MTSLRData.type == 'PReq').all()
print(f"Total PReq records in mt_slr_data: {len(slr_preqs)}")

mod_slr = []
for s in slr_preqs:
    desc = str(s.description or '')
    if any(k in desc.lower() for k in ['module', 'panel', 'solar', 'pv']):
        mod_slr.append(s)

print(f"Module/solar related PReqs in mt_slr_data: {len(mod_slr)}")
for s in mod_slr[:10]:
    print(f"  PO/Doc: {s.purchasing_doc}, Plant: {s.plant_prefix}, Desc: {s.description}, Comm: Rs {s.commitment_inr/1e7:.2f} Cr, Act: Rs {s.actual_inr/1e7:.2f} Cr")

db.close()
