import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
from models import ProjectMapping

db = SessionLocal()
mappings = db.query(ProjectMapping).all()
for m in mappings:
    print(f"Project: {m.project_id}, Capacity: {getattr(m, 'capacity_mwac', 'N/A')}")
