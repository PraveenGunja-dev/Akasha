import os
import pandas as pd

data_dir = r"d:\Akasha_Platform\Data\NEW31"
me2j_path = os.path.join(data_dir, "Me2J 1.xlsx")
zsps_path = os.path.join(data_dir, "ZPSPS007 1.xlsx")

print("Reading Me2J 1.xlsx...")
df_me2j = pd.read_excel(me2j_path, usecols=['Purchasing Document'])
me2j_docs = set(df_me2j['Purchasing Document'].dropna().astype(str).str.strip().str.replace('.0', '', regex=False))
print(f"Total Unique POs in ME2J: {len(me2j_docs)}")

print("Reading ZPSPS007 1.xlsx...")
df_zsps = pd.read_excel(zsps_path, usecols=['C.Document'])
zsps_docs = set(df_zsps['C.Document'].dropna().astype(str).str.strip().str.replace('.0', '', regex=False))
print(f"Total Unique POs in ZSPS (unfiltered): {len(zsps_docs)}")

matching_docs = me2j_docs.intersection(zsps_docs)
missing_docs = me2j_docs - zsps_docs

print(f"\n--- Results ---")
print(f"POs in ME2J that ARE ALSO in ZSPS: {len(matching_docs)}")
print(f"POs in ME2J that ARE MISSING from ZSPS: {len(missing_docs)}")
