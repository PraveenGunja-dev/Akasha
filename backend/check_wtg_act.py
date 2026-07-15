import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import P6Activity, P6WBSNode

db = SessionLocal()
acts = db.query(P6Activity).filter(P6Activity.name.ilike('%WTG%')).filter(P6Activity.name.ilike('%COD%')).limit(10).all()
print("COD WTG Activities:")
for a in acts:
    print(a.name)

tr_acts = db.query(P6Activity).filter(P6Activity.name.ilike('%WTG%')).filter(P6Activity.name.ilike('%Trial%')).limit(10).all()
print("\nTrial WTG Activities:")
for a in tr_acts:
    print(a.name)
db.close()
