import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import P6WBSNode, P6Project, P6Activity
import re

db = SessionLocal()
p = db.query(P6Project).filter(P6Project.project_id == 'FY26-P20').first()
if p:
    print(f"Project: {p.name}")
    wbs = db.query(P6WBSNode).filter(P6WBSNode.project_object_id == p.p6_object_id).all()
    for w in wbs:
        if 'CONSTRUCTION' in (w.wbs_name or '').upper() or 'BLOCK' in (w.wbs_name or '').upper():
            print(f"WBS Node: {w.wbs_name} | ID: {w.p6_object_id} | Parent: {w.parent_object_id}")
            
    # Also check what activities we found
    acts = db.query(P6Activity).filter(P6Activity.project_object_id == p.p6_object_id).all()
    for a in acts:
        m = re.search(r'(Block-\d+|WTG\s*\d+)', a.name or "", re.IGNORECASE)
        if m:
            print(f"Activity Block Match: {a.name} | WBS Name: {a.wbs_name}")
db.close()
