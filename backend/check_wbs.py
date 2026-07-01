import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
from models import P6Activity

db = SessionLocal()
activities = db.query(P6Activity).filter(P6Activity.name.ilike('%Block-08%')).all()
for a in activities:
    print(f"Name: {a.name}, WBS: {a.wbs_object_id}")
