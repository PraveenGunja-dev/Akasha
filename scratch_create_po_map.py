import pandas as pd
import json
import os
import gc

def create_po_map():
    data_dir = r"D:\Akasha_Platform\Data\NEW31"
    me2j_path = os.path.join(data_dir, "Me2J 1.xlsx")
    out_path = os.path.join(data_dir, "me2j_po_lookup.json")
    
    print("Reading ME2J...")
    df = pd.read_excel(me2j_path, usecols=['Purchasing Document', 'Buyer Name', 'Document Date', 'Storage Location', 'Material', 'Plant', 'Currency', 'Delivery Completed'])
    print("Dropping duplicates...")
    df = df.drop_duplicates(subset=['Purchasing Document'])
    
    # Convert dates to string so they can be JSON serialized
    if 'Document Date' in df.columns:
        df['Document Date'] = df['Document Date'].astype(str)
        
    print("Converting to dict...")
    po_lookup = df.set_index('Purchasing Document').to_dict('index')
    
    # Handle NaNs
    import math
    def clean_dict(d):
        return {k: (v if v == v else None) for k, v in d.items()}
    
    po_lookup_clean = {str(k): clean_dict(v) for k, v in po_lookup.items()}
    
    print("Writing JSON...")
    with open(out_path, 'w') as f:
        json.dump(po_lookup_clean, f)
    
    print(f"Created lookup with {len(po_lookup_clean)} entries at {out_path}")

if __name__ == "__main__":
    create_po_map()
