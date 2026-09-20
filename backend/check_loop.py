import os
from dotenv import load_dotenv
load_dotenv(override=True)
from database import SessionLocal
from sqlalchemy import text
import models
import re

db = SessionLocal()

all_p6_ftc = db.execute(text("""
    SELECT p.project_id, a.name, a.planned_finish_date
    FROM p6_activity a
    JOIN p6_project p ON p.p6_object_id = a.project_object_id
    WHERE (a.name ILIKE '%First Time Charging%' OR a.name ILIKE '%FTC%')
      AND a.type = 'Finish Milestone'
      AND a.planned_finish_date IS NOT NULL AND p.project_id IS NOT NULL
    ORDER BY a.planned_finish_date ASC
""")).fetchall()

ftc_phases_by_pid = {}
for row in all_p6_ftc:
    pid, name, dt = row[0], row[1], row[2]
    match = re.search(r'(Phase[\s\-]*[IV]+)', name, re.IGNORECASE)
    phase = ""
    if match:
        phase_num = match.group(1).upper().replace('PHASE', '').replace('-', '').strip()
        phase = f"Ph-{phase_num}"
    ftc_phases_by_pid.setdefault(pid, []).append((phase, dt))

print("Dict size:", len(ftc_phases_by_pid))
print("Dict keys:", list(ftc_phases_by_pid.keys())[:5])

mappings = db.query(models.ProjectMapping).filter(
    models.ProjectMapping.capacity_mwac.isnot(None),
    models.ProjectMapping.capacity_mwac > 0,
    models.ProjectMapping.category != 'Wind',
    models.ProjectMapping.mms_type != 'Wind',
).all()

count = 0
for m in mappings:
    ftc_list = ftc_phases_by_pid.get(m.project_id, [])
    if ftc_list:
        count += 1
        
print("Matches in loop:", count)
