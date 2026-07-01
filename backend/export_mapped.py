import sys
sys.path.append('d:\\Akasha_Platform\\backend')

from database import SessionLocal
import models
import pandas as pd
from routers.dashboard import get_dashboard_summary

db = SessionLocal()
data = get_dashboard_summary(nocache=True, db=db)
projects = data.get('projects', [])

mapped = []
for p in projects:
    tc = p.get('tc', {})
    tc_has_data = tc.get('has_data', False)
    if tc_has_data:
        # Fetch SPV Name directly from DB using mapping_id
        mapping = db.query(models.ProjectMapping).filter(models.ProjectMapping.id == p.get('mapping_id')).first()
        spv_name = mapping.spv_name if mapping else ''
        
        khavda_count = len(tc.get('data', {}).get('khavda', []))
        rajasthan_count = len(tc.get('data', {}).get('rajasthan', []))
        
        mapped.append({
            'Project': p.get('project_name', ''),
            'SPV Name': spv_name,
            'SPV Plant Code': p.get('spv_plant_code', ''),
            'P6 ID': p.get('p6', {}).get('id', ''),
            'P6 Name': p.get('p6_project_name', ''),
            'Transmission Status': tc.get('status', ''),
            'Khavda Edges': khavda_count,
            'Rajasthan Edges': rajasthan_count
        })

df = pd.DataFrame(mapped)
output_path = 'd:\\Akasha_Platform\\Mapped_Transmission_Projects.xlsx'
df.to_excel(output_path, index=False)
print(f'Successfully exported {len(mapped)} mapped projects to {output_path}')
