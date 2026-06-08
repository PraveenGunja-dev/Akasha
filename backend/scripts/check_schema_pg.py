import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from database import SessionLocal
from models import ProjectMapping
from sqlalchemy import inspect
from database import engine

db = SessionLocal()

# Check actual columns using SQLAlchemy inspector
inspector = inspect(engine)
columns = inspector.get_columns('project_mapping')
print("Actual ProjectMapping Columns in DB:")
for col in columns:
    print(f"  - {col['name']} ({col['type']})")

print("\nSample Mappings:")
mappings = db.query(ProjectMapping).limit(5).all()
for m in mappings:
    print(f"ID: {m.id}, P6: {m.p6_project_name}, SAP: {m.sap_plant_code}, AGEL: {m.agel_code}, WBS: {m.module_wbs}")

# Check if there is a 'project' column manually in case it's an attribute
if hasattr(ProjectMapping, 'project'):
    print("\nYES! ProjectMapping has a 'project' attribute/column!")

db.close()
