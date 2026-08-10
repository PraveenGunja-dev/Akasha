import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from database import SessionLocal
import models
from sqlalchemy import text

def ingest_mapping():
    db = SessionLocal()
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Data")
    mapping_file_old = os.path.join(data_dir, "Project_Name_Master.xlsx")
    
    # Try preferred AKASHA SAP MASTER FILE.xlsx first
    mapping_file_new = os.path.join(data_dir, "AKASHA SAP MASTER FILE.xlsx")
    if not os.path.exists(mapping_file_new):
        mapping_file_new = os.path.join(data_dir, "SAP Master sheet AKASHA (1).xlsx")
    
    try:
        # Create table if not exists
        models.Base.metadata.create_all(bind=db.get_bind())
        
        print("Clearing old mapping data and unlinking foreign keys...")
        db.execute(text("UPDATE tc_project_entry SET mapping_id = NULL"))
        db.execute(text("UPDATE tc_network_edge SET mapping_id = NULL"))
        db.query(models.ProjectMapping).delete()
        db.commit()

        print(f"Reading new mapping {os.path.basename(mapping_file_new)}...")
        df_new = pd.read_excel(mapping_file_new)
        
        if os.path.exists(mapping_file_old):
            print(f"Reading old mapping {os.path.basename(mapping_file_old)}...")
            df_old = pd.read_excel(mapping_file_old)
            print("Merging mapping data...")
            df = pd.merge(df_new, df_old, left_on='P6 ID', right_on='Project ID', how='left').fillna("")
        else:
            df = df_new.fillna("")
        
        mappings = []
        for _, row in df.iterrows():
            project = str(row.get('Project', '')).strip()
            plot_no = str(row.get('Plot No', '')).strip()
            category = str(row.get('Category', '')).strip()
            mms_type = str(row.get('MMS Type', '')).strip()
            ol = str(row.get('OL', '')).strip()
            wbs = str(row.get('Module WBS', '')).strip()
            not_allocated = str(row.get('Not Allocated', '')).strip()
            priority = str(row.get('Priority', '')).strip()
            source_of_origin = str(row.get('SourceOfOrigin', '')).strip()
            
            project_id = str(row.get('P6 ID', '')).strip()
            project_name_from_p6 = str(row.get('Project Name', '')).strip()
            if not project:
                project = project_name_from_p6
                
            spv_name = str(row.get('SPV', '')).strip()
            # Plant code might be 'Plant code ', 'Plant code', or fallback 'SPV.1'
            plant_code = str(row.get('Plant code ', row.get('Plant code', row.get('SPV.1', '')))).strip()
            agel = str(row.get('AGEL', '')).strip()
            age6l = str(row.get('AGE6L', '')).strip()
            cluster = str(row.get('Type (Cluster)', row.get('Cluster', ''))).strip()
            
            # Safely parse capacity
            def parse_float(val):
                try:
                    return float(str(val).strip())
                except ValueError:
                    return 0.0
                    
            cap_ac = parse_float(row.get('Capacity\n(MWac)', ''))
            cap_dc = parse_float(row.get('Capacity (MWdc)', ''))
            
            if project_id:  # Removed plant_code check since some projects don't have it
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
                    not_allocated=not_allocated,
                    priority=priority,
                    source_of_origin=source_of_origin
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
