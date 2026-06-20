import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import dotenv
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

from database import SessionLocal
import models
from sqlalchemy import func

db = SessionLocal()

# Get all mappings
mappings = db.query(models.ProjectMapping).all()
valid_wbs_prefixes = set()
valid_plant_codes = set()

for m in mappings:
    if m.module_wbs:
        valid_wbs_prefixes.add(m.module_wbs[:6])
    if m.spv_plant_code:
        valid_plant_codes.add(str(m.spv_plant_code).strip())
    if m.agel:
        valid_plant_codes.add(str(m.agel).strip())

# Get unique WBS and Plant from ME2K
me2k_data = db.query(models.MTPOAmount.wbs_element, models.MTPOAmount.plant_code).distinct().all()

unmapped = []
for wbs, plant in me2k_data:
    wbs_str = str(wbs).strip() if wbs else ""
    plant_str = str(plant).strip() if plant else ""
    
    is_mapped_wbs = False
    for prefix in valid_wbs_prefixes:
        if wbs_str.startswith(prefix):
            is_mapped_wbs = True
            break
            
    is_mapped_plant = plant_str in valid_plant_codes
    
    if not (is_mapped_wbs and is_mapped_plant):
        unmapped.append((wbs_str, plant_str))

# Group by WBS prefix for a cleaner output
unmapped_projects = set()
for wbs, plant in unmapped:
    prefix = wbs[:6] if wbs and len(wbs) >= 6 else wbs
    unmapped_projects.add((prefix, plant))

print(f"Total distinct (WBS, Plant) in ME2K: {len(me2k_data)}")
print(f"Total unmapped combinations: {len(unmapped)}")
print(f"Unmapped Projects (WBS Prefix, Plant):")
for proj in sorted(list(unmapped_projects)):
    print(f"WBS Prefix: {proj[0]}, Plant Code: {proj[1]}")

db.close()
