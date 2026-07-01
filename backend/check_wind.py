import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
from models import ProjectMapping

db = SessionLocal()
mappings = db.query(ProjectMapping).filter(ProjectMapping.category.ilike('%wind%') | ProjectMapping.project_name_from_p6.ilike('%wind%')).all()
for m in mappings:
    print(f"ID: {m.project_id}, Name: {m.project_name_from_p6}, Cap: {m.capacity_mwac}, Type: {m.mms_type}, Category: {m.category}")
