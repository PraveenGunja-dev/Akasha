import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import ProjectMapping

db = SessionLocal()
mappings = db.query(ProjectMapping).all()
for m in mappings:
    print(m.project_id, m.project, m.project_name_from_p6)
