import re
from database import SessionLocal
from models import ProjectMapping

db = SessionLocal()
m = db.query(ProjectMapping).filter(ProjectMapping.project_id=='FY25-P15').first()
if m:
    w = []
    for val in [m.spv_plant_code, m.agel, m.age6l]:
        if val:
            matches = [c.strip()[:6] for c in re.findall(r'H-\S+', str(val).strip()) if len(c.strip()) >= 6]
            w.extend(matches)
            w.extend([ma.replace('-', '') for ma in matches])
    print("Prefixes:", list(set(w)))
    print("SPV:", m.spv_plant_code)
    print("AGEL:", m.agel)
    print("AGE6L:", m.age6l)
else:
    print("Not found")
