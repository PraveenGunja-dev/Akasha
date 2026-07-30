import sys
import os

# Add backend dir to path
sys.path.append(os.path.abspath("d:/Akasha_Platform/backend"))

from database import SessionLocal
import models

db = SessionLocal()

print("Querying ProjectMapping for FY25-P06...")
pm = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id == "FY25-P06").first()
if not pm:
    print("No mapping found for FY25-P06!")
    sys.exit(0)

print(f"SPV Code: {pm.spv_plant_code}")
print(f"AGEL Code: {pm.agel}")
print(f"AGE6L Code: {pm.age6l}")

codes = []
if pm.spv_plant_code: codes.append(str(pm.spv_plant_code).strip())
if pm.agel: codes.append(str(pm.agel).strip())
if pm.age6l: codes.append(str(pm.age6l).strip())

print(f"Codes to query in SLR Data: {codes}")

if not codes:
    print("No plant codes to query SLR data!")
    sys.exit(0)

slr_records = db.query(models.MTSLRData).filter(models.MTSLRData.plant_code.in_(codes)).all()
print(f"Found {len(slr_records)} SLR records for these codes.")

if slr_records:
    print("Sample record:", slr_records[0].__dict__)
