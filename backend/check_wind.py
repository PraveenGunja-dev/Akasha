import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import MTTrialRun, ProjectMapping

db = SessionLocal()

wind_trs = db.query(MTTrialRun).filter(MTTrialRun.unit_of_measure == 'Wind').all()
wind_mws = set()
for tr in wind_trs:
    wind_mws.add((tr.project_name_p6, tr.tr_quantity_mw))

print("Wind MTTrialRun capacities:")
for w in list(wind_mws)[:20]:
    print(w)
    
db.close()
