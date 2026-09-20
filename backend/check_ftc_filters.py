import os
from dotenv import load_dotenv
load_dotenv(override=True)
from database import SessionLocal
from sqlalchemy import text
import models

db = SessionLocal()

# 1. Fetch FTC from P6 with Project ID
res = db.execute(text("""
    SELECT p.project_id, a.name, a.planned_finish_date
    FROM p6_activity a
    JOIN p6_project p ON p.p6_object_id = a.project_object_id
    WHERE (a.name ILIKE '%First Time Charging%' OR a.name ILIKE '%FTC%')
      AND a.type = 'Finish Milestone'
      AND a.planned_finish_date IS NOT NULL AND p.project_id IS NOT NULL
""")).fetchall()
p6_ids = {r[0] for r in res}

# 2. Fetch Project IDs from project_mapping WITH SAME FILTERS AS ENDPOINT
mappings = db.query(models.ProjectMapping).filter(
    models.ProjectMapping.capacity_mwac.isnot(None),
    models.ProjectMapping.capacity_mwac > 0,
    models.ProjectMapping.category != 'Wind',
    models.ProjectMapping.mms_type != 'Wind',
).all()

pm_ids = {m.project_id for m in mappings if m.project_id}

print(f"Total mappings after filter: {len(mappings)}")
print(f"Valid mapping project_ids: {len(pm_ids)}")
print(f"Intersection with P6 FTC: {len(p6_ids.intersection(pm_ids))}")
