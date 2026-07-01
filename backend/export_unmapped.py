import sys
sys.path.append('d:\\Akasha_Platform\\backend')

from database import SessionLocal
import models
import pandas as pd
from routers.dashboard import get_dashboard_summary

db = SessionLocal()
data = get_dashboard_summary(nocache=True, db=db)
projects = data.get('projects', [])

unmapped = []
for p in projects:
    tc_has_data = p.get('tc', {}).get('has_data', False)
    if not tc_has_data:
        # Fetch SPV Name directly from DB using mapping_id
        mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == p.get('mapping_id')).first()
        spv_name = mapping.spv_name if mapping else ''
        
        unmapped.append({
            'Project': p.get('project_name', ''),
            'SPV Name': spv_name,
            'SPV Plant Code': p.get('spv_plant_code', ''),
            'P6 ID': p.get('p6', {}).get('id', ''),
            'P6 Name': p.get('p6_project_name', '')
        })

df = pd.DataFrame(unmapped)
output_path = 'd:\\Akasha_Platform\\Unmapped_Transmission_Projects.xlsx'
df.to_excel(output_path, index=False)
print(f'Successfully exported {len(unmapped)} projects to {output_path}')
