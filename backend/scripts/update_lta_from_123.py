import sys
import os
import pandas as pd
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
import models

def main():
    db = SessionLocal()
    file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "123_export.xlsx")
    
    print(f"Reading {file_path}")
    try:
        df = pd.read_excel(file_path, header=4)
    except Exception as e:
        print(f"Failed to read excel: {e}")
        return
        
    p6_col = None
    project_col = None
    ecod_col = None
    
    # The actual column names are scattered. We search row 0 for the column names.
    for col in df.columns:
        val = str(df.at[0, col]).strip()
        if val == 'P6 project Name':
            p6_col = col
        elif val == 'Project':
            project_col = col
        elif val == 'ECOD':
            ecod_col = col

    if not ecod_col:
        print("Could not find ECOD column in row 0")
        return
        
    updated_count = 0
    # Skip row 0 (which contains sub-headers)
    for idx in range(1, len(df)):
        row = df.iloc[idx]
        p6_name = str(row.get(p6_col, '')).strip() if p6_col else ''
        project = str(row.get(project_col, '')).strip() if project_col else ''
        ecod_val = row.get(ecod_col)
        
        if pd.isna(ecod_val) or str(ecod_val).strip() == '' or str(ecod_val) == 'nan':
            continue
            
        try:
            ecod_date = pd.to_datetime(ecod_val)
        except Exception:
            continue
            
        mapping = None
        if p6_name and p6_name != 'nan':
            mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_name_from_p6 == p6_name).first()
        
        if not mapping and project and project != 'nan':
            mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.project == project).first()
            
        if mapping:
            mapping.lta_date = ecod_date
            updated_count += 1
        else:
            print(f"Could not find mapping for P6 project: {p6_name} or Project: {project}")
            
    db.commit()
    print(f"Updated {updated_count} records with LTA dates.")

if __name__ == "__main__":
    main()
