import os
import pandas as pd
import sys

data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Data")
me2j_path = os.path.join(data_dir, "ME2J.XLSX")

df_me2j = pd.read_excel(me2j_path)
if 'WBS Element' in df_me2j.columns:
    df_me2j['WBS_Element_Clean'] = df_me2j['WBS Element'].astype(str).str.strip()
else:
    df_me2j['WBS_Element_Clean'] = df_me2j['WBS element'].astype(str).str.strip()

wbs = "H-51GA-01-01"
df_wbs_me2j = df_me2j[df_me2j['WBS_Element_Clean'] == wbs]

# Filter statistical
df_wbs_me2j = df_wbs_me2j[df_wbs_me2j['Statistical'].isna() | (df_wbs_me2j['Statistical'].astype(str).str.strip() == '') | (df_wbs_me2j['Statistical'].astype(str).str.lower() == 'nan')]

print(f"Non-Statistical Rows for {wbs}: {len(df_wbs_me2j)}")

def safe_float(val):
    if pd.isna(val): return 0.0
    s = str(val).strip()
    if not s or s.lower() in ('nan', 'none', ''): return 0.0
    s = s.replace(',', '')
    if s.endswith('-'): s = '-' + s[:-1]
    try: return float(s)
    except: return 0.0

total_ordered = sum(safe_float(x) for x in df_wbs_me2j['Order Quantity'])
total_pending = sum(safe_float(x) for x in df_wbs_me2j['Still to be delivered (qty)'])
total_value = sum(safe_float(x) for x in df_wbs_me2j['PO Value in Local Currency'])
total_pending_val = sum(safe_float(x) for x in df_wbs_me2j['PO Pending Value in Local Currency'])

print(f"Total Ordered: {total_ordered:,.2f}")
print(f"Still to be Delivered (Qty): {total_pending:,.2f}")
print(f"PO Value INR: {total_value:,.2f}")
print(f"Pending Value INR: {total_pending_val:,.2f}")
