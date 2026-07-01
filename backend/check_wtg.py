import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
from models import P6Activity

db = SessionLocal()
wtg_acts = db.query(P6Activity).filter(P6Activity.name.ilike('%wtg%'), P6Activity.name.ilike('%cod%')).limit(15).all()
for a in wtg_acts:
    print(f"Name: {a.name}, WBS Name: {a.wbs_name}")
