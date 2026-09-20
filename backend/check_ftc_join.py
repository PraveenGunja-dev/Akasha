import os
from dotenv import load_dotenv
load_dotenv(override=True)
from database import SessionLocal
from sqlalchemy import text

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
print("P6 FTC project IDs:", len(p6_ids), list(p6_ids)[:5])

# 2. Fetch Project IDs from project_mapping
pm = db.execute(text("SELECT project_id FROM project_mapping WHERE project_id IS NOT NULL")).fetchall()
pm_ids = {r[0] for r in pm}
print("ProjectMapping IDs:", len(pm_ids), list(pm_ids)[:5])

# 3. Check intersection
intersection = p6_ids.intersection(pm_ids)
print("\nIntersection size:", len(intersection))
print("Intersection:", intersection)
