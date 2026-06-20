import re
from database import SessionLocal
from models import P6Project, ProjectMapping

WIND_PROJECTS = {
    "3074": 5.2,
    "4707": 5.0,
    "3075": 5.2,
    "3076": 5.2,
    "3072": 5.2,
    "3073": 5.2,
    "6733": 5.2,
    "3105": 3.3
}

db = SessionLocal()

def extract_capacity(name, mw_mult):
    locs = re.findall(r'(\d+)\s*Loc', name, flags=re.IGNORECASE)
    if not locs:
        return mw_mult * 10  # default guess
    return sum(int(l) for l in locs) * mw_mult

for pid, mult in WIND_PROJECTS.items():
    p6 = db.query(P6Project).filter(P6Project.p6_object_id == pid).first()
    if p6:
        existing = db.query(ProjectMapping).filter(ProjectMapping.project_name_from_p6 == str(p6.project_id)).first()
        if not existing:
            mw = extract_capacity(p6.name, mult)
            pm = ProjectMapping(
                project="Wind - " + p6.name,
                project_name_from_p6=str(p6.project_id),
                capacity_mwac=mw,
                spv_name=p6.name.split(" ")[0] if " " in p6.name else p6.name,
                category="Wind",
                mms_type="Wind",
                module_wbs="Wind",
                spv_plant_code="WIND_"+pid,
                project_id=str(p6.project_id)
            )
            db.add(pm)
            print(f"Added {p6.name} with capacity {mw} MW")
        else:
            print(f"Already exists: {p6.name}")

db.commit()
db.close()
