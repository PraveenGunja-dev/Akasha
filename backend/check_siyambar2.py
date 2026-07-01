import sys
sys.path.append('d:\\Akasha_Platform\\backend')
import json
from database import SessionLocal
import models
from routers.dashboard import get_dashboard_summary

db = SessionLocal()
data = get_dashboard_summary(nocache=True, db=db)
projects = data.get('projects', [])

for p in projects:
    if 'siyamb' in str(p.get('p6_project_name')).lower() or 'siyamb' in str(p.get('project_name')).lower():
        print(f"Project: {p.get('p6_project_name')}")
        print(f"TC Data: {json.dumps(p.get('tc'), indent=2)}")
