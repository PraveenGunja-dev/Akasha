import os
import sys
import pandas as pd

new_file = r"d:\adani\Akasha\Data\19_09\ZPSPS007 4.XLSX"
df_new = pd.read_excel(new_file)

preqs_new = df_new[df_new['Type'].astype(str).str.strip() == 'PReq']
print(f"Total PReq rows in new file: {len(preqs_new)}")

open_qty_new = preqs_new[preqs_new['C.Quantity'] > 0]
open_amt_new = preqs_new[preqs_new['Commitment Amt'] > 0]

print(f"PReqs with open C.Quantity > 0 in new file: {len(open_qty_new)}")
print(f"PReqs with open Commitment Amt > 0 in new file: {len(open_amt_new)}")

if not open_qty_new.empty:
    print(open_qty_new[['C.Document', 'WBS Element', 'Short text', 'C.Quantity', 'Commitment Amt']])
else:
    print(">>> ZERO open PReqs in the new file (all have 0 quantity and 0 amount).")

# Also check for any PO/PReq with 'MSEDCL', 'SECI', 'NHPC', 'MLP' in Description or WBS
print("\nChecking if any rows in new file mention MSEDCL / SECI / NHPC / MLP:")
for kw in ['MSEDCL', 'SECI', 'NHPC', 'MLP']:
    match = df_new[df_new['Description'].astype(str).str.contains(kw, case=False, na=False)]
    print(f"  Keyword '{kw}': {len(match)} rows found in new file.")
