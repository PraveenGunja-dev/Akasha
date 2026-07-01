import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
from models import P6Project, ProjectMapping

db = SessionLocal()
p = db.query(P6Project).first()
print(f"P6Project: p6_object_id: {p.p6_object_id}, project_id: {p.project_id}")
m = db.query(ProjectMapping).filter(ProjectMapping.project_id == p.project_id).first()
if m:
    print(f"Mapped Capacity: {m.capacity_mwac}")
