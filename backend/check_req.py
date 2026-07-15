import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import MTRequirement

db = SessionLocal()

wind_req = db.query(MTRequirement).filter(MTRequirement.unit_of_measure == 'Wind').all()
wind_mws = set()
for r in wind_req:
    wind_mws.add((r.project_name_p6, r.budgeted_units_mw))

print("Wind MTRequirement capacities:")
for w in list(wind_mws)[:20]:
    print(w)
    
db.close()
