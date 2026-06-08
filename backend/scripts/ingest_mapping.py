import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from database import SessionLocal
import models
from sqlalchemy import text

def ingest_mapping():
    db = SessionLocal()
    mapping_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data", "Project_Name_Master (1).xlsx")
    
    try:
        # Create table if not exists
        models.Base.metadata.create_all(bind=db.get_bind())
        
        print("Clearing old mapping data...")
        db.query(models.ProjectMapping).delete()
        db.commit()

        print(f"Reading {mapping_file}...")
        df = pd.read_excel(mapping_file).fillna("")
        
        mappings = []
        for _, row in df.iterrows():
            project = str(row.get('Project', '')).strip()
            spv_name = str(row.get('SPVName', '')).strip()
            project_id = str(row.get('Project ID', '')).strip()
            project_name_from_p6 = str(row.get('Project name from\nP6', '')).strip()
            plot_no = str(row.get('Plot No', '')).strip()
            category = str(row.get('Category', '')).strip()
            mms_type = str(row.get('MMS Type', '')).strip()
            ol = str(row.get('OL', '')).strip()
            plant_code = str(row.get('SPVPlantCode', '')).strip()
            agel = str(row.get('AGEL', '')).strip()
            wbs = str(row.get('Module WBS', '')).strip()
            age6l = str(row.get('AGE6L', '')).strip()
            cluster = str(row.get('Cluster', '')).strip()
            not_allocated = str(row.get('Not Allocated', '')).strip()
            
            # Safely parse capacity
            def parse_float(val):
                try:
                    return float(str(val).strip())
                except ValueError:
                    return 0.0
                    
            cap_ac = parse_float(row.get('Capacity\n(MWac)', ''))
            cap_dc = parse_float(row.get('Capacity (MWdc)', ''))
            
            if project_id and plant_code:
                mapping = models.ProjectMapping(
                    project=project,
                    spv_name=spv_name,
                    project_id=project_id,
                    project_name_from_p6=project_name_from_p6,
                    plot_no=plot_no,
                    category=category,
                    mms_type=mms_type,
                    capacity_mwac=cap_ac,
                    ol=ol,
                    capacity_mwdc=cap_dc,
                    spv_plant_code=plant_code,
                    agel=agel,
                    module_wbs=wbs,
                    age6l=age6l,
                    cluster=cluster,
                    not_allocated=not_allocated
                )
                mappings.append(mapping)
                
        db.add_all(mappings)
        db.commit()
        print(f"Successfully ingested {len(mappings)} project mappings!")
        
    except Exception as e:
        db.rollback()
        print(f"Error ingesting mapping: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    ingest_mapping()
