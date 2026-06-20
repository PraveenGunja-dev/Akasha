import os
import sys
sys.path.append(os.getcwd())
from backend.database import SessionLocal
from backend import models

db = SessionLocal()
mappings = db.query(models.ProjectMapping).all()
mapped_count = 0
mapped_projects = []

for m in mappings:
    wbs_prefix = m.module_wbs[:6] if m.module_wbs else None
    if not wbs_prefix:
        continue
    pos = db.query(models.MTPOAmount).filter(models.MTPOAmount.wbs_element.startswith(wbs_prefix)).count()
    if pos > 0:
        mapped_count += 1
        mapped_projects.append(m.project)

print(f'Total Mapped Projects: {mapped_count}')
for p in mapped_projects:
    print(f" - {p}")
