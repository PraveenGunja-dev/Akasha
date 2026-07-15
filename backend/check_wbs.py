import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import ProjectMapping, P6Activity, P6Project, P6WBSNode

db = SessionLocal()

proj = db.query(ProjectMapping).filter(ProjectMapping.project_name_from_p6 == 'ACL_A1_FT_125MW_GROUP_Commissioned').first()
p6 = db.query(P6Project).filter(P6Project.project_id == proj.project_id).first()

wbs = db.query(P6WBSNode).filter(P6WBSNode.project_object_id == p6.p6_object_id).all()
blocks = [w.wbs_name for w in wbs if 'BLOCK' in w.wbs_name.upper()]
print(f"Total WBS blocks for ACL: {len(blocks)}")
print(blocks)

db.close()
