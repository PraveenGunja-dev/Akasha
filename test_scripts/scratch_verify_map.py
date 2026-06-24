import sys
import os
import json
from dotenv import load_dotenv

load_dotenv('backend/.env')
sys.path.append(os.path.abspath('backend'))
from database import SessionLocal
from models import ProjectMapping

db = SessionLocal()

with open('user_mapping.json') as f:
    user_data = json.load(f)

mismatches = []
matches = []

for item in user_data:
    t_proj = item['Project']
    p6_proj = item['P6_Project_Name']
    
    if not p6_proj: continue
    
    # Get all DB mappings for this Transmission Project
    db_maps_by_t = db.query(ProjectMapping).filter(ProjectMapping.project == t_proj).all()
    db_maps_by_p6 = db.query(ProjectMapping).filter(ProjectMapping.project_name_from_p6 == p6_proj).all()
    
    # Is there a perfect match?
    perfect_match = False
    for m in db_maps_by_t:
        if m.project_name_from_p6 == p6_proj:
            perfect_match = True
            break
            
    if perfect_match:
        matches.append(f'MATCH: {t_proj} -> {p6_proj}')
    else:
        # Check what the DB actually has
        t_mapped_to_p6 = [m.project_name_from_p6 for m in db_maps_by_t]
        p6_mapped_to_t = [m.project for m in db_maps_by_p6]
        
        if len(db_maps_by_t) == 0 and len(db_maps_by_p6) == 0:
            mismatches.append(f'MISSING in DB: Transmission="{t_proj}", P6="{p6_proj}"')
        else:
            msg = f'MISMATCH: {t_proj} -> {p6_proj}\n'
            if t_mapped_to_p6:
                msg += f'  DB says Transmission "{t_proj}" is mapped to P6: {t_mapped_to_p6}\n'
            if p6_mapped_to_t:
                msg += f'  DB says P6 "{p6_proj}" is mapped to Transmission: {p6_mapped_to_t}'
            mismatches.append(msg)

print(f'\nTotal Matches: {len(matches)}')
for m in matches: print(m)

print(f'\nTotal Mismatches/Missing: {len(mismatches)}')
for m in mismatches: print(m)
