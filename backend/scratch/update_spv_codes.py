import os
import sys
import pandas as pd

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

from database import SessionLocal
import models
from sqlalchemy import update

def run_update():
    file_path = os.path.join(os.path.dirname(backend_dir), "Data", "SAP Master sheet AKASHA (1).xlsx")
    
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return
        
    print(f"Reading {file_path}...")
    try:
        df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error reading excel: {e}")
        return
        
    db = SessionLocal()
    updated_count = 0
    try:
        for _, row in df.iterrows():
            project_id = str(row.get('P6 ID', '')).strip()
            if not project_id or project_id.lower() == 'nan':
                continue
                
            spv_plant_code = str(row.get('SPV.1', '')).strip()
            agel = str(row.get('AGEL', '')).strip()
            age6l = str(row.get('AGE6L', '')).strip()
            
            if spv_plant_code.lower() == 'nan': spv_plant_code = ""
            if agel.lower() == 'nan': agel = ""
            if age6l.lower() == 'nan': age6l = ""
            
            stmt = (
                update(models.ProjectMapping)
                .where(models.ProjectMapping.project_id == project_id)
                .values(spv_plant_code=spv_plant_code, agel=agel, age6l=age6l)
            )
            result = db.execute(stmt)
            updated_count += result.rowcount
            
        db.commit()
        print(f"Successfully updated {updated_count} project mapping rows with SPV.1, AGEL, and AGE6L codes!")
    except Exception as e:
        db.rollback()
        print(f"Database error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_update()
