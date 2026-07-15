import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from models import ProjectMapping, P6Activity, P6Project, MTTrialRun
import re

db = SessionLocal()

proj = db.query(ProjectMapping).filter(ProjectMapping.project_name_from_p6 == 'ACL_A1_FT_125MW_GROUP_Commissioned').first()
p6 = db.query(P6Project).filter(P6Project.project_id == proj.project_id).first()

# Get all COD activities in P6
cod_acts = db.query(P6Activity).filter(P6Activity.project_object_id == p6.p6_object_id, P6Activity.name.ilike('%COD%')).all()

blocks = {}
for a in cod_acts:
    # extract block name, usually "Block-05 -COD"
    m = re.match(r'(Block-\d+)', a.name, re.IGNORECASE)
    if m:
        b = m.group(1).upper()
        if b not in blocks:
            blocks[b] = {'cod': a.status, 'tr': 'Not Started'}
        else:
            blocks[b]['cod'] = a.status

# Get Trial Run acts
tr_acts = db.query(P6Activity).filter(P6Activity.project_object_id == p6.p6_object_id, P6Activity.name.ilike('%Trial%')).all()
for a in tr_acts:
    m = re.match(r'(Block-\d+)', a.name, re.IGNORECASE)
    if m:
        b = m.group(1).upper()
        if b in blocks:
            blocks[b]['tr'] = a.status
        else:
            blocks[b] = {'cod': 'Not Started', 'tr': a.status}

for b, status in blocks.items():
    print(f"{b}: COD={status.get('cod')} | TR={status.get('tr')}")

# Match with MW from MTTrialRun
trs = db.query(MTTrialRun).filter(MTTrialRun.project_name_p6 == 'ACL_A1_FT_125 MW_GROUP_Commissioned').all()
tr_mw = {}
for tr in trs:
    b = tr.project_name_block.upper()
    if 'COD' in tr.activity_name:
        tr_mw[b] = tr.tr_quantity_mw

for b, mw in tr_mw.items():
    print(f"MTTrialRun MW for {b}: {mw}")

db.close()
