import sys
sys.path.append('d:\\Akasha_Platform\\backend')

from database import SessionLocal
import models
from routers.dashboard import get_dashboard_summary

db = SessionLocal()
data = get_dashboard_summary(nocache=True, db=db)
projects = data.get('projects', [])

total = len(projects)
mapped = 0
unmapped = 0

for p in projects:
    if p.get('tc', {}).get('has_data', False):
        mapped += 1
    else:
        unmapped += 1

print(f'Total Projects: {total}')
print(f'Mapped to Transmission: {mapped}')
print(f'Unmapped: {unmapped}')
