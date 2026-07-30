import os
import pandas as pd

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
input_file = os.path.join(os.path.dirname(backend_dir), "Data", "ZPSPS007.XLSX")
output_file = os.path.join(os.path.dirname(backend_dir), "Data", "ZPSPS007_Filtered.xlsx")

print(f"Reading {input_file}...")
df = pd.read_excel(input_file)

initial_count = len(df)
print(f"Initial row count: {initial_count}")

# Filter 1: Remove where Actual Amount AND Commitment Amt are both zero (or empty/NaN)
# Fill NaN with 0 for these columns to safely check for 0
actual_amt = pd.to_numeric(df['Actual Amount'], errors='coerce').fillna(0)
comm_amt = pd.to_numeric(df['Commitment Amt'], errors='coerce').fillna(0)

# Keep rows where Actual != 0 OR Commitment != 0
mask_not_both_zero = (actual_amt != 0) | (comm_amt != 0)
df_filtered = df[mask_not_both_zero]

print(f"Rows after removing Actual=0 & Commitment=0: {len(df_filtered)}")

# Filter 2: Filter out 'X' from the first column ('Summary')
# We assume the first column is 'Summary', and we want to remove rows where it equals 'X' (case insensitive)
if 'Summary' in df_filtered.columns:
    summary_col = df_filtered['Summary'].astype(str).str.strip().str.upper()
    df_filtered = df_filtered[summary_col != 'X']
    print(f"Rows after removing 'X' from Summary column: {len(df_filtered)}")
else:
    print("Warning: 'Summary' column not found!")

# Save to new Excel file
print(f"Saving filtered data to {output_file}...")
df_filtered.to_excel(output_file, index=False)
print("Done!")
