import pandas as pd
import sys

def analyze_excel(file_path):
    try:
        print(f"Reading {file_path}...")
        df = pd.read_excel(file_path, sheet_name=None)
        for sheet_name, sheet_df in df.items():
            print(f"\n--- Sheet: {sheet_name} ---")
            print("Columns:", list(sheet_df.columns))
            print(f"Total rows: {len(sheet_df)}")
            
            # Show a sample of the first 3 rows
            print("\nFirst 3 rows:")
            print(sheet_df.head(3).to_string())
            
            # If there's a column about 'active' or codes like AGEL, AGE6L, we can summarize
            # Let's just print unique values for some potential key columns if they exist
            for col in sheet_df.columns:
                if 'status' in str(col).lower() or 'active' in str(col).lower():
                    print(f"\nValue counts for '{col}':")
                    print(sheet_df[col].value_counts().to_string())
                if 'code' in str(col).lower() or 'spc' in str(col).lower():
                    unique_vals = sheet_df[col].dropna().unique()
                    print(f"\nUnique values for '{col}' (first 10): {unique_vals[:10]}")
                    
    except Exception as e:
        print(f"Error reading Excel file: {e}")

if __name__ == "__main__":
    file_path = r"d:\Akasha_Platform\Data\SAP Master sheet AKASHA (1).xlsx"
    analyze_excel(file_path)
