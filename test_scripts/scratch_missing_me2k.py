import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import dotenv
dotenv.load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

from database import SessionLocal
import models
from sqlalchemy import func

db = SessionLocal()

# 1. Get all mappings (Projects)
mappings = db.query(models.ProjectMapping).all()

# 2. Get unique WBS and Plant from ME2K
me2k_data = db.query(models.MTPOAmount.wbs_element, models.MTPOAmount.plant_code).distinct().all()

# Create quick lookups for ME2K data
me2k_wbs_prefixes = set()
me2k_plants = set()

for wbs, plant in me2k_data:
    if wbs:
        me2k_wbs_prefixes.add(str(wbs).strip()[:6])
    if plant:
        me2k_plants.add(str(plant).strip())

projects_without_me2k = []

for m in mappings:
    has_me2k = False
    
    # Extract prefixes/codes for this project
    proj_wbs_prefix = str(m.module_wbs).strip()[:6] if m.module_wbs else None
    proj_plant_codes = set()
    if m.spv_plant_code:
        proj_plant_codes.add(str(m.spv_plant_code).strip())
    if m.agel:
        proj_plant_codes.add(str(m.agel).strip())
        
    # Logic: a project HAS ME2K data if its WBS prefix is in the ME2K WBS prefixes 
    # AND at least one of its plant codes is in the ME2K plant codes.
    # Actually, let's just query the db to be 100% accurate per project.
    
    if proj_wbs_prefix and proj_plant_codes:
        count = db.query(models.MTPOAmount).filter(
            models.MTPOAmount.plant_code.in_(list(proj_plant_codes)),
            models.MTPOAmount.wbs_element.startswith(proj_wbs_prefix)
        ).count()
        if count > 0:
            has_me2k = True
            
    if not has_me2k:
        # Provide a readable project name
        name = m.project_name_from_p6 or m.project or f"Project ID: {m.project_id}"
        projects_without_me2k.append({
            "name": name,
            "project_id": m.project_id,
            "wbs": m.module_wbs,
            "spv": m.spv_name
        })

print(f"Total mapped projects: {len(mappings)}")
print(f"Projects with NO ME2K data: {len(projects_without_me2k)}")
print("-" * 50)
for p in projects_without_me2k:
    print(f"• {p['name']} (ID: {p['project_id']}, WBS: {p['wbs']}, SPV: {p['spv']})")

db.close()
