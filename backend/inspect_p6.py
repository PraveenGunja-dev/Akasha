import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import ProjectMapping, P6Activity, P6Project, P6WBSNode

db = SessionLocal()

# Check ACL project
proj = db.query(ProjectMapping).filter(ProjectMapping.project_name_from_p6 == 'ACL_A1_FT_125MW_GROUP_Commissioned').first()
p6 = db.query(P6Project).filter(P6Project.project_id == proj.project_id).first()

print(f"Project: {proj.project_name_from_p6} (ID: {proj.project_id}, p6_object_id: {p6.p6_object_id})")

# Look at WBS nodes
wbs = db.query(P6WBSNode).filter(P6WBSNode.project_object_id == p6.p6_object_id).all()
print(f"Total WBS nodes: {len(wbs)}")
for w in wbs[:10]:
    print(f"WBS: {w.wbs_name} (Code: {w.wbs_code})")

# Look at P6Activity with 'COD' in name
cod_acts = db.query(P6Activity).filter(P6Activity.project_object_id == p6.p6_object_id, P6Activity.name.ilike('%COD%')).all()
print(f"\nCOD Activities: {len(cod_acts)}")
for a in cod_acts:
    print(f" - {a.activity_id}: {a.name} | Status: {a.status} | WBS: {a.wbs_name}")

# Look at P6Activity with 'Trial' in name
tr_acts = db.query(P6Activity).filter(P6Activity.project_object_id == p6.p6_object_id, P6Activity.name.ilike('%Trial%')).all()
print(f"\nTrial Run Activities: {len(tr_acts)}")
for a in tr_acts[:5]:
    print(f" - {a.activity_id}: {a.name} | Status: {a.status} | WBS: {a.wbs_name}")

db.close()
