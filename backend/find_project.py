import os, sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
from models import ProjectMapping
from services.project_service import get_project_360_detail

db = SessionLocal()
maps = db.query(ProjectMapping.project_id).all()
for m in maps:
    p_id = m[0]
    res = get_project_360_detail(db, p_id)
    if res and res.get('sap'):
        budget = res['sap']['summary']['totalBudgetINR'] / 10000000
        if 99 < budget < 102:
            print(p_id, budget)
