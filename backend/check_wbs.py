import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv(override=True)
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Count by WBS name
rows = db.execute(text("""
    SELECT a.wbs_name, COUNT(*) as cnt
    FROM p6_activity a
    JOIN p6_project p ON p.p6_object_id = a.project_object_id
    WHERE (a.name ILIKE '%First Time Charging%' OR a.name ILIKE '%FTC%')
      AND a.type = 'Finish Milestone'
      AND a.planned_finish_date IS NOT NULL AND p.project_id IS NOT NULL
    GROUP BY a.wbs_name
    ORDER BY cnt DESC
""")).fetchall()

print("=== FTC activities by WBS name ===")
total = 0
for r in rows:
    print(f"  {r[0]}: {r[1]}")
    total += r[1]
print(f"  TOTAL: {total}")

# Show sample of MILESTONES-only vs all
milestones_only = db.execute(text("""
    SELECT p.project_id, a.name, a.planned_finish_date, a.wbs_name
    FROM p6_activity a
    JOIN p6_project p ON p.p6_object_id = a.project_object_id
    WHERE (a.name ILIKE '%First Time Charging%' OR a.name ILIKE '%FTC%')
      AND a.type = 'Finish Milestone'
      AND a.planned_finish_date IS NOT NULL AND p.project_id IS NOT NULL
      AND a.wbs_name = 'MILESTONES'
    ORDER BY p.project_id, a.planned_finish_date
""")).fetchall()

print(f"\n=== MILESTONES WBS only: {len(milestones_only)} activities ===")
for r in milestones_only[:10]:
    print(f"  {r[0]} | {r[1]} | {r[2].strftime('%d-%b-%y')} | WBS={r[3]}")

# Compare: projects with FTC from any WBS vs MILESTONES only
all_pids = db.execute(text("""
    SELECT DISTINCT p.project_id
    FROM p6_activity a
    JOIN p6_project p ON p.p6_object_id = a.project_object_id
    WHERE (a.name ILIKE '%First Time Charging%' OR a.name ILIKE '%FTC%')
      AND a.type = 'Finish Milestone'
      AND a.planned_finish_date IS NOT NULL AND p.project_id IS NOT NULL
""")).fetchall()

ms_pids = db.execute(text("""
    SELECT DISTINCT p.project_id
    FROM p6_activity a
    JOIN p6_project p ON p.p6_object_id = a.project_object_id
    WHERE (a.name ILIKE '%First Time Charging%' OR a.name ILIKE '%FTC%')
      AND a.type = 'Finish Milestone'
      AND a.planned_finish_date IS NOT NULL AND p.project_id IS NOT NULL
      AND a.wbs_name = 'MILESTONES'
""")).fetchall()

all_set = {r[0] for r in all_pids}
ms_set = {r[0] for r in ms_pids}
print(f"\nProjects with FTC (any WBS): {len(all_set)}")
print(f"Projects with FTC (MILESTONES only): {len(ms_set)}")
print(f"Projects that would LOSE FTC: {all_set - ms_set}")

db.close()
