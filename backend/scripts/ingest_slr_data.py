import os
import sys
import pandas as pd

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

from database import SessionLocal, engine
import models

def ingest_slr():
    file_path = os.path.join(os.path.dirname(backend_dir), "Data", "ZPSPS007_Filtered.xlsx")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
        
    print(f"Reading {file_path}...")
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error reading excel: {e}")
        return
        
    # Ensure table exists
    models.MTSLRData.__table__.create(bind=engine, checkfirst=True)
    
    db = SessionLocal()
    
    # Wipe old data
    print("Deleting old SLR data...")
    db.query(models.MTSLRData).delete()
    db.commit()
    
    slr_records = []
    
    print("Parsing records...")
    for _, row in df.iterrows():
        wbs_val = str(row.get('WBS Element', '')).strip()
        if not wbs_val or wbs_val.lower() == 'nan':
            continue
            
        po_doc = str(row.get('A.Document', '')).strip()
        if po_doc.lower() == 'nan': po_doc = ""
            
        desc = str(row.get('Description', '')).strip()
        if desc.lower() == 'nan': desc = ""
            
        type_val = str(row.get('Type', '')).strip()
        if type_val.lower() == 'nan': type_val = ""
        
        # Safely parse floats
        try:
            actual = float(row.get('Actual Amount', 0))
            if pd.isna(actual): actual = 0.0
        except: actual = 0.0
        
        try:
            comm = float(row.get('Commitment Amt', 0))
            if pd.isna(comm): comm = 0.0
        except: comm = 0.0
            
        prefix = wbs_val[:6]
        
        record = models.MTSLRData(
            po_document=po_doc,
            description=desc,
            actual_amount=actual,
            commitment_amount=comm,
            wbs_element=wbs_val,
            type=type_val,
            plant_code=prefix
        )
        slr_records.append(record)
        
    print(f"Bulk inserting {len(slr_records)} records...")
    db.bulk_save_objects(slr_records)
    db.commit()
    db.close()
    
    print("Done!")

if __name__ == "__main__":
    ingest_slr()
