import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
import models
from routers.dashboard import get_dashboard_summary
import json

db = SessionLocal()
data = get_dashboard_summary(nocache=True, db=db)
projects = data.get('projects', [])

for p in projects:
    if 'bandha' in str(p.get('p6_project_name')).lower() or 'bandha' in str(p.get('project_name')).lower():
        print(f"Project: {p.get('p6_project_name')}")
        print(f"Transmission Status: {p.get('tc', {}).get('status')}")
        
        khavda_edges = len(p.get('tc', {}).get('data', {}).get('khavda', []))
        rajasthan_edges = len(p.get('tc', {}).get('data', {}).get('rajasthan', []))
        print(f"Khavda Edges: {khavda_edges}")
        print(f"Rajasthan Edges: {rajasthan_edges}")
