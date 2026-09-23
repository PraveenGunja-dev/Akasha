import os
import sys
import pandas as pd
import numpy as np

backend_dir = r"d:\adani\Akasha\backend"
sys.path.insert(0, backend_dir)

from database import SessionLocal
import models
from services.module_wattage import module_watts

new_file = r"d:\adani\Akasha\Data\19_09\ZPSPS007 4.XLSX"
old_file = r"d:\adani\Akasha\Data\19_09\ZPSPS007.xlsx"

print("=" * 80)
print("1. LOADING NEW FILE: ZPSPS007 4.XLSX")
print("=" * 80)
df_new = pd.read_excel(new_file)
print(f"Total rows: {len(df_new)}")
print(f"Columns: {list(df_new.columns)}")

# Identify date columns and numeric columns in df_new
date_cols = [c for c in df_new.columns if any(k in c.lower() for k in ['date', 'dt', 'time', 'day', 'deliv', 'sched', 'valid'])]
print(f"Date columns found in new file: {date_cols}")

print("\nSample values of first 3 rows in new file:")
print(df_new[['C.Document', 'C.Document line', 'WBS Element', 'Short text', 'C.Quantity', 'A.Quantity', 'Commitment Amt', 'Actual Amount'] + [c for c in date_cols if c in df_new.columns]].head(3))

print("\n" + "=" * 80)
print("2. LOADING OLD FILE: ZPSPS007.xlsx")
print("=" * 80)
# We can load the relevant columns or all
df_old = pd.read_excel(old_file)
print(f"Total rows in old file: {len(df_old)}")
print(f"Columns in old file: {list(df_old.columns)}")

# Clean up keys for comparison
def make_clean_key(df):
    po = df['C.Document'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    line = df['C.Document line'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True) if 'C.Document line' in df.columns else '0'
    wbs = df['WBS Element'].astype(str).str.strip() if 'WBS Element' in df.columns else ''
    return po + "_" + line + "_" + wbs

df_new['key'] = make_clean_key(df_new)
df_old['key'] = make_clean_key(df_old)

new_keys = set(df_new['key'])
old_keys = set(df_old['key'])

print(f"\nUnique (PO, Line, WBS) in new file: {len(new_keys)}")
print(f"Unique (PO, Line, WBS) in old file: {len(old_keys)}")

extra_in_new = new_keys - old_keys
print(f"\nKeys in new file but NOT in old file: {len(extra_in_new)}")
if extra_in_new:
    print("Found EXTRA records in new file:")
    print(df_new[df_new['key'].isin(extra_in_new)][['C.Document', 'C.Document line', 'WBS Element', 'Short text', 'C.Quantity', 'A.Quantity']])
else:
    print(">>> 0 completely new (PO, Line, WBS) keys. All keys in new file exist in old file.")

# Check PO level
new_pos = set(df_new['C.Document'].dropna().astype(str).str.strip().str.replace(r'\.0$', '', regex=True))
old_pos = set(df_old['C.Document'].dropna().astype(str).str.strip().str.replace(r'\.0$', '', regex=True))
print(f"\nUnique POs in new file: {len(new_pos)}")
print(f"Unique POs in old file: {len(old_pos)}")
extra_pos = new_pos - old_pos
print(f"POs in new file but NOT in old file: {len(extra_pos)}")
if extra_pos:
    print("Extra PO numbers:", extra_pos)

print("\n" + "=" * 80)
print("3. CHECKING QUANTITY DIFFERENCES (C.Quantity & A.Quantity)")
print("=" * 80)
# Merge on key to compare
merged = pd.merge(df_new, df_old, on='key', suffixes=('_new', '_old'))
print(f"Matching rows between new and old on key: {len(merged)}")

# Compare C.Quantity (Commitment/Pending Quantity)
merged['c_qty_new'] = pd.to_numeric(merged['C.Quantity_new'], errors='coerce').fillna(0)
merged['c_qty_old'] = pd.to_numeric(merged['C.Quantity_old'], errors='coerce').fillna(0)
merged['c_qty_diff'] = merged['c_qty_new'] - merged['c_qty_old']

# Compare A.Quantity (Actual/Delivered Quantity)
merged['a_qty_new'] = pd.to_numeric(merged['A.Quantity_new'], errors='coerce').fillna(0)
merged['a_qty_old'] = pd.to_numeric(merged['A.Quantity_old'], errors='coerce').fillna(0)
merged['a_qty_diff'] = merged['a_qty_new'] - merged['a_qty_old']

# Total qty
merged['tot_qty_new'] = merged['c_qty_new'] + merged['a_qty_new']
merged['tot_qty_old'] = merged['c_qty_old'] + merged['a_qty_old']
merged['tot_qty_diff'] = merged['tot_qty_new'] - merged['tot_qty_old']

diff_c_qty = merged[merged['c_qty_diff'] != 0]
diff_a_qty = merged[merged['a_qty_diff'] != 0]
diff_tot_qty = merged[merged['tot_qty_diff'] != 0]

print(f"Rows with differing C.Quantity (Commitment/Pending): {len(diff_c_qty)}")
print(f"Rows with differing A.Quantity (Actual/Delivered):    {len(diff_a_qty)}")
print(f"Rows with differing Total Quantity (C + A):          {len(diff_tot_qty)}")

if len(diff_tot_qty) > 0:
    print("\nRows with different Total Quantity:")
    print(diff_tot_qty[['C.Document_new', 'Short text_new', 'tot_qty_old', 'tot_qty_new', 'tot_qty_diff']].head(10))

if len(diff_a_qty) > 0:
    print("\nRows with different Actual (Delivered) Quantity:")
    print(diff_a_qty[['C.Document_new', 'Short text_new', 'a_qty_old', 'a_qty_new', 'a_qty_diff']].head(10))

if len(diff_c_qty) > 0:
    print("\nRows with different Commitment (Pending) Quantity:")
    print(diff_c_qty[['C.Document_new', 'Short text_new', 'c_qty_old', 'c_qty_new', 'c_qty_diff']].head(10))

print("\n" + "=" * 80)
print("4. CHECKING DATES")
print("=" * 80)
# Look at all columns in df_new and df_old that might be dates
all_cols_new = df_new.columns.tolist()
all_cols_old = df_old.columns.tolist()
print("All columns in new file:")
for c in all_cols_new:
    print(f"  - {c} (type: {df_new[c].dtype})")

# Let's inspect ME2J or mt_me2j_po for PO dates
print("\n" + "=" * 80)
print("5. CHECKING DATABASE mt_poamount")
print("=" * 80)
db = SessionLocal()
live_pos = db.query(models.MTPOAmount).filter(models.MTPOAmount.purchasing_document.in_(list(new_pos))).all()
print(f"Count of matching PO records in live mt_poamount: {len(live_pos)}")

# Check MWp calculation
total_mwp_new = 0
for idx, r in df_new.iterrows():
    st = str(r.get('Short text', ''))
    w = module_watts(st)
    c_q = pd.to_numeric(r.get('C.Quantity', 0), errors='coerce') or 0
    a_q = pd.to_numeric(r.get('A.Quantity', 0), errors='coerce') or 0
    tot_q = c_q + a_q
    if w:
        total_mwp_new += (tot_q * w) / 1e6

print(f"Total MWp calculated across all rows in new file: {total_mwp_new:.2f} MWp")
db.close()
