import os
import sys
sys.path.append(os.getcwd())
from database import SessionLocal
import models
from sqlalchemy import func

db = SessionLocal()

# 1. Get all unique WBS prefixes (first 6 chars) from POs
po_wbs_records = db.query(models.MTPOAmount.wbs_element).distinct().all()
po_prefixes = {}
for rec in po_wbs_records:
    wbs = rec[0]
    if wbs:
        prefix = wbs.strip()[:6]
        if prefix not in po_prefixes:
            po_prefixes[prefix] = 0
        
        # Count how many PO records have this WBS prefix
        count = db.query(models.MTPOAmount).filter(models.MTPOAmount.wbs_element.startswith(prefix)).count()
        po_prefixes[prefix] = count

# 2. Get all known WBS prefixes from ProjectMappings
known_mappings = db.query(models.ProjectMapping.module_wbs).distinct().all()
known_prefixes = set()
for m in known_mappings:
    wbs = m[0]
    if wbs:
        known_prefixes.add(wbs.strip()[:6])

# 3. Find missing
missing_prefixes = []
for prefix, count in po_prefixes.items():
    if prefix not in known_prefixes:
        missing_prefixes.append((prefix, count))

missing_prefixes.sort(key=lambda x: x[1], reverse=True)

print(f"Total Unique WBS Prefixes in POs: {len(po_prefixes)}")
print(f"Total Known WBS Prefixes in Projects: {len(known_prefixes)}")
print(f"Missing WBS Prefixes (Not mapped to any project): {len(missing_prefixes)}")
for p, c in missing_prefixes:
    print(f" - {p} ({c} PO records)")
