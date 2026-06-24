import os
import pandas as pd

mb51_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Data", "MB51_Khavda_Mat_Consumption_221_222 2 (2).XLSX")
df_mb51 = pd.read_excel(mb51_path)

def parse_qty(val):
    if pd.isna(val): return 0.0
    s = str(val).strip().replace(',', '')
    if s.endswith('-'): s = '-' + s[:-1]
    try: return float(s)
    except: return 0.0

df_mb51['Parsed_Qty'] = df_mb51['Quantity'].apply(parse_qty)

print("Sum of 221 (Parsed):", df_mb51[df_mb51['Movement_Type'] == 221]['Parsed_Qty'].sum())
print("Sum of 222 (Parsed):", df_mb51[df_mb51['Movement_Type'] == 222]['Parsed_Qty'].sum())

wbs = "H-51GA-01-01"
df_mb51['WBS_Element_Clean'] = df_mb51['WBS_Element'].astype(str).str.strip()
df_wbs = df_mb51[df_mb51['WBS_Element_Clean'] == wbs]

print(f"\nFor WBS {wbs}:")
print("Sum of 221:", df_wbs[df_wbs['Movement_Type'] == 221]['Parsed_Qty'].sum())
print("Sum of 222:", df_wbs[df_wbs['Movement_Type'] == 222]['Parsed_Qty'].sum())
