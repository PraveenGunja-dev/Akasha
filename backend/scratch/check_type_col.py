import os
import pandas as pd

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
file_path = os.path.join(os.path.dirname(backend_dir), "Data", "ZPSPS007.XLSX")

print(f"Reading {file_path}...")
df = pd.read_excel(file_path)

print("\n--- Unique values in 'Type' column ---")
print(df['Type'].value_counts(dropna=False))

print("\n--- Sample of 'P ord' rows ---")
print(df[df['Type'] == 'P ord'].head(2).to_string())

print("\n--- Sample of 'P req' rows ---")
print(df[df['Type'] == 'P req'].head(2).to_string())
