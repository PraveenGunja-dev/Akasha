import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from models import MTTrialRun, ProjectMapping, P6Project

db = SessionLocal()

print("--- MTTrialRun Projects ---")
trs = db.query(MTTrialRun.project_name, MTTrialRun.project_name_p6).distinct().all()
for t in trs:
    print(t)

print("\n--- ProjectMapping Projects ---")
pms = db.query(ProjectMapping.project_id, ProjectMapping.project_name_from_p6, ProjectMapping.project).distinct().all()
for p in pms:
    print(p)
    
print("\n--- P6Project Projects ---")
p6s = db.query(P6Project.project_id, P6Project.name).distinct().all()
for p in p6s:
    print(p)
    
db.close()
