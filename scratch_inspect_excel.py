import pandas as pd
import os

data_dir = r'd:\Akasha_Platform\Data\NEW31'
me2j_path = os.path.join(data_dir, "Me2J 1.xlsx")

df = pd.read_excel(me2j_path, nrows=10)

print("All column names:")
for i, col in enumerate(df.columns):
    print(f"  {i}: '{col}' (type={type(col).__name__})")

print()
print("WBS-related columns:")
for col in df.columns:
    if 'wbs' in str(col).lower():
        print(f"  Column '{col}':")
        print(f"    Values: {df[col].head(10).tolist()}")

print()
print("First 5 rows WBS values using .get():")
for idx, row in df.head(5).iterrows():
    wbs_upper = row.get('WBS Element', 'NOT FOUND')
    wbs_lower = row.get('WBS element', 'NOT FOUND')
    print(f"  Row {idx}: WBS Element='{wbs_upper}', WBS element='{wbs_lower}'")
