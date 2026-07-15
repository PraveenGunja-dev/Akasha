import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import ProjectMapping, MTTrialRun, P6Activity, P6Project
import docx

db = SessionLocal()

projects = db.query(ProjectMapping).all()
print(f"Total projects in mapping: {len(projects)}")

for p in projects[:3]:
    print(f"\nProject: {p.project_name_from_p6} (WBS: {p.module_wbs})")
    p6_proj = db.query(P6Project).filter(P6Project.project_id == p.project_id).first()
    
    if p6_proj:
        obj_id = p6_proj.p6_object_id
        cod_acts = db.query(P6Activity).filter(P6Activity.project_object_id == obj_id, P6Activity.name.ilike('%COD%')).all()
        tr_acts = db.query(P6Activity).filter(P6Activity.project_object_id == obj_id, P6Activity.name.ilike('%Trial%')).all()
        print(f"  COD acts: {len(cod_acts)}, completed: {sum(1 for a in cod_acts if a.status == 'Completed')}")
        print(f"  TR acts: {len(tr_acts)}, completed: {sum(1 for a in tr_acts if a.status == 'Completed')}")
    else:
        print("  Not found in p6_project")

db.close()
