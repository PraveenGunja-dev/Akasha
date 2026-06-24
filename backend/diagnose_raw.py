import os
import pandas as pd

data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Data")

mb51_path = os.path.join(data_dir, "MB51_Khavda_Mat_Consumption_221_222 2 (2).XLSX")
me2j_path = os.path.join(data_dir, "ME2J.XLSX")

print("--- Diagnostics for MB51 ---")
df_mb51 = pd.read_excel(mb51_path)
print("Unique Movement Types:", df_mb51['Movement_Type'].unique())

wbs = "H-51GA-01-01"
# Clean WBS
df_mb51['WBS_Element'] = df_mb51['WBS_Element'].astype(str).str.strip()

df_wbs_mb51 = df_mb51[df_mb51['WBS_Element'] == wbs]
print(f"Total MB51 rows for {wbs}:", len(df_wbs_mb51))
print("Sum of MB51 Quantity for WBS:", df_wbs_mb51['Quantity'].sum())

print("\n--- Diagnostics for ME2J ---")
df_me2j = pd.read_excel(me2j_path)
if 'WBS Element' in df_me2j.columns:
    df_me2j['WBS_Element_Clean'] = df_me2j['WBS Element'].astype(str).str.strip()
else:
    df_me2j['WBS_Element_Clean'] = df_me2j['WBS element'].astype(str).str.strip()

df_wbs_me2j = df_me2j[df_me2j['WBS_Element_Clean'] == wbs]
print(f"Total ME2J rows for {wbs}:", len(df_wbs_me2j))
print("Sum of ME2J Order Quantity for WBS:", df_wbs_me2j['Order Quantity'].sum())

# Are there any Statistical = x rows for this WBS?
stat_x = df_wbs_me2j[df_wbs_me2j['Statistical'].astype(str).str.lower() == 'x']
print(f"ME2J rows with Statistical = 'x' for this WBS: {len(stat_x)}, Quantity: {stat_x['Order Quantity'].sum()}")
