"""Check project_mapping for Mundra North Wind."""
import sys; sys.path.insert(0, '.')
from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

# Search project_mapping for anything wind/mundra related
print("=== project_mapping Wind/Mundra ===")
rows = db.execute(text(
    "SELECT id, project, spv_name, project_id, project_name_from_p6, category, mms_type, capacity_mwac, spv_plant_code, agel, age6l, cluster "
    "FROM project_mapping "
    "WHERE project ILIKE '%mundra%' OR project ILIKE '%wind%' OR project_name_from_p6 ILIKE '%mundra%' OR category ILIKE '%wind%'"
)).fetchall()
for r in rows:
    print(dict(zip(['id','project','spv_name','project_id','p6_name','category','mms_type','cap_mwac','spv_plant','agel','age6l','cluster'], r)))

# Also check p6_project for any wind project
print("\n=== p6_project with MUNDRA in name ===")
rows = db.execute(text(
    "SELECT p6_object_id, project_id, name, status, start_date, scheduled_finish_date, data_date, location_name, parent_eps_name, activity_count "
    "FROM p6_project WHERE name ILIKE '%MUNDRA%'"
)).fetchall()
for r in rows:
    print(dict(zip(['p6_oid','proj_id','name','status','start','sched_finish','data_date','location','parent_eps','act_count'], r)))

# Check SAP summary - total PO amounts for the WBS
print("\n=== SAP Total PO Amount for Mundra WBS ===")
rows = db.execute(text(
    "SELECT wbs_element, SUM(CAST(NULLIF(po_amount, '') AS NUMERIC)) as total "
    "FROM mt_poamount WHERE wbs_element LIKE 'H-51YV%' OR wbs_element LIKE 'H-62YV%' "
    "GROUP BY wbs_element ORDER BY total DESC LIMIT 15"
)).fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]}")

db.close()
