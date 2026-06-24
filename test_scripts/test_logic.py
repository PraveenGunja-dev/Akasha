import sys
import os
import re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import SessionLocal
from models import MTTrialRun, ProjectMapping, P6Project

db = SessionLocal()

WIND_PROJECTS = {
    "3074": 5.2, "4707": 5.0, "3075": 5.2, "3076": 5.2,
    "3072": 5.2, "3073": 5.2, "6733": 5.2, "3105": 3.3,
    "MUNDRA NORTH NEW": 3.3
}
DEFAULT_WIND_MW = 5.2

def get_total_wtgs(name):
    import re
    matches = re.findall(r'(\d+)\s*Loc', name, re.IGNORECASE)
    return sum(int(m) for m in matches) if matches else 0

p6s = db.query(P6Project).all()
p6_map = {p.name: p.project_id for p in p6s if p.name}

trs = db.query(MTTrialRun).filter(MTTrialRun.unit_of_measure == "Wind").all()
projects = {}
for m in trs:
    p_name = m.project_name or m.project_name_p6 or "Unknown"
    
    if p_name not in projects:
        proj_id = p6_map.get(p_name)
        wtg_mw = WIND_PROJECTS.get(proj_id, DEFAULT_WIND_MW)
        total_wtg = get_total_wtgs(p_name)
        total_cap = total_wtg * wtg_mw
        
        projects[p_name] = {
            'proj_id': proj_id,
            'wtg_mw': wtg_mw,
            'total_wtg': total_wtg,
            'total_cap': total_cap
        }

for k, v in projects.items():
    print(f"{k} -> ID: {v['proj_id']} | WTG MW: {v['wtg_mw']} | Total WTG: {v['total_wtg']} | Total Cap: {v['total_cap']}")

db.close()
