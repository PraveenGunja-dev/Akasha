import pandas as pd
import os

filepath = r'd:\Akasha_Platform\Data\NEW31\ZPSPS007 (3).xlsx'

try:
    print(f"Reading file: {filepath}")
    df = pd.read_excel(filepath)
    
    print("\n--- File Summary ---")
    print(f"Total Rows: {len(df)}")
    print(f"Total Columns: {len(df.columns)}")
    
    print("\n--- Columns ---")
    for i, col in enumerate(df.columns):
        print(f"  {i}: {col}")
        
    print("\n--- Project/WBS Columns Analysis ---")
    # Try to find columns that might represent Project or WBS
    for col in df.columns:
        if any(keyword in str(col).lower() for keyword in ['wbs', 'project', 'plant', 'spv']):
            unique_vals = df[col].dropna().unique()
            print(f"\nColumn '{col}':")
            print(f"  Total Unique Values: {len(unique_vals)}")
            
            # Extract project prefixes (e.g., 'H-6061' -> '6061')
            prefixes = set()
            for val in unique_vals:
                val_str = str(val).strip().upper()
                if val_str.startswith('H-'):
                    parts = val_str.split('-')
                    if len(parts) >= 2:
                        prefixes.add(parts[1])
            
            print(f"  Total Unique Projects (Prefixes): {len(prefixes)}")
            print(f"  Project Prefixes: {sorted(list(prefixes))}")

except Exception as e:
    print(f"Error reading file: {e}")
