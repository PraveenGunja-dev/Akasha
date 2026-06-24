import os
import sys
import pandas as pd

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

import models
from database import SessionLocal

def export_missing_me2k_to_excel():
    db = SessionLocal()
    mappings = db.query(models.ProjectMapping).all()
    
    missing_projects = []
    
    for m in mappings:
        has_me2k = False
        plant_codes = []
        if m.spv_plant_code and str(m.spv_plant_code).strip().lower() not in ('nan', 'none', ''):
            plant_codes.append(str(m.spv_plant_code).strip())
        if m.agel and str(m.agel).strip().lower() not in ('nan', 'none', ''):
            plant_codes.append(str(m.agel).strip())
            
        wbs_prefix = ""
        if m.module_wbs and str(m.module_wbs).strip().lower() not in ('nan', 'none', ''):
            wbs_prefix = str(m.module_wbs).strip()[:6]
            
        if plant_codes:
            query = db.query(models.MTPOAmount).filter(models.MTPOAmount.plant_code.in_(plant_codes))
            if wbs_prefix:
                query = query.filter(models.MTPOAmount.wbs_element.startswith(wbs_prefix))
            count = query.count()
            if count > 0:
                has_me2k = True
                
        if not has_me2k:
            missing_projects.append({
                "Mapping_ID": m.id,
                "Project_Name_P6": m.project_name_from_p6,
                "SPV_Plant_Code": m.spv_plant_code,
                "AGEL_Code": m.agel,
                "Module_WBS": m.module_wbs,
                "Capacity_MWac": m.capacity_mwac
            })
            
    df = pd.DataFrame(missing_projects)
    output_path = os.path.join(backend_dir, "Projects_Missing_ME2K_Data.xlsx")
    df.to_excel(output_path, index=False)
    
    print(f"Exported {len(missing_projects)} projects to {output_path}")

if __name__ == "__main__":
    export_missing_me2k_to_excel()
