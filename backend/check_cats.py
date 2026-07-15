import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import ProjectMapping

db = SessionLocal()
projects = db.query(ProjectMapping).all()
cats = set()
for p in projects:
    cats.add((p.category, p.project_name_from_p6, p.capacity_mwac, p.capacity_mwdc))
    if len(cats) > 10:
        break
for c in cats:
    print(c)
db.close()
