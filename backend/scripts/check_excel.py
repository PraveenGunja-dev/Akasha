import pandas as pd
import os

file_path = r"d:\Akasha_Platform\Data\Project_Name_Master (1).xlsx"
print(f"Reading {file_path}...")
df = pd.read_excel(file_path)
print("Columns in Excel file:")
for col in df.columns:
    print(f" - {col}")
