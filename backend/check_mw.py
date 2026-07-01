import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
from models import P6Activity

db = SessionLocal()
cod_acts = db.query(P6Activity).filter(P6Activity.name.ilike('%cod%') | P6Activity.name.ilike('%trial%') | P6Activity.name.ilike('%trail%')).limit(15).all()
for a in cod_acts:
    print(f"Name: {a.name}, WBS Name: {a.wbs_name}")
