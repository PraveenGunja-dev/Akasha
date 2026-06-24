import os
import sys
import pandas as pd

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

import models
from database import SessionLocal

def export_all_mappings_to_excel():
    db = SessionLocal()
    mappings = db.query(models.ProjectMapping).all()
    
    all_projects = []
    
    for m in mappings:
        all_projects.append({
            "Mapping_ID": m.id,
            "Project_Name_P6": m.project_name_from_p6,
            "SPV_Plant_Code": m.spv_plant_code,
            "AGEL_Code": m.agel,
            "Module_WBS": m.module_wbs,
            "Capacity_MWac": m.capacity_mwac
        })
            
    df = pd.DataFrame(all_projects)
    output_path = os.path.join(backend_dir, "All_Project_Mappings.xlsx")
    df.to_excel(output_path, index=False)
    
    print(f"Exported {len(all_projects)} projects to {output_path}")

if __name__ == "__main__":
    export_all_mappings_to_excel()
