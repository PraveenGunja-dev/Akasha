import sys
import os
import re
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import P6WBSNode, P6Project, P6Activity

def normalize_block(name):
    name = name.replace(" ", "").upper()
    m = re.match(r'(BLOCK-|WTG-?)0+(\d+)', name)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return name

db = SessionLocal()
p = db.query(P6Project).filter(P6Project.project_id == 'FY26-P20').first()
if p:
    obj_id = p.p6_object_id
    wbs_nodes = db.query(P6WBSNode).filter(P6WBSNode.project_object_id == obj_id).all()
    all_blocks = set()
    for w in wbs_nodes:
        m = re.search(r'(Block-\d+|WTG\s*\d+)', w.wbs_name or "", re.IGNORECASE)
        if m:
            all_blocks.add(normalize_block(m.group(1)))
    
    cod_acts = db.query(P6Activity).filter(P6Activity.project_object_id == obj_id, P6Activity.name.ilike('%COD%')).all()
    tr_acts = db.query(P6Activity).filter(P6Activity.project_object_id == obj_id, P6Activity.name.ilike('%Trial%')).all()
    for a in cod_acts + tr_acts:
        m = re.search(r'(Block-\d+|WTG\s*\d+)', a.name or "", re.IGNORECASE)
        if m:
            all_blocks.add(normalize_block(m.group(1)))
            
    print(f"Normalized WBS Blocks: {all_blocks}")
db.close()
