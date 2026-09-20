import pandas as pd
import sys

file_path = r'd:\Akasha_Platform\Data\20260904_Connectivity_r1Share.xlsx'
try:
    df = pd.read_excel(file_path)
    with open(r'C:\Users\USER\.gemini\antigravity-ide\brain\4a4a94fa-5cd0-46a2-a26e-87a61705a967\scratch\excel_dump2.txt', 'w', encoding='utf-8') as f:
        f.write("Columns in 20260904_Connectivity_r1Share.xlsx:\n")
        f.write(str(df.columns.tolist()) + "\n\n")
        f.write("First 15 rows:\n")
        f.write(df.head(15).to_string())
except Exception as e:
    print(f"Error: {e}")
