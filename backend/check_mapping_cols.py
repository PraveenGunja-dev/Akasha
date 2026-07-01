import sys
sys.path.append('d:\\Akasha_Platform\\backend')
from database import SessionLocal
from models import ProjectMapping

db = SessionLocal()
mappings = db.query(ProjectMapping).all()
first_mapping = mappings[0]
print("Columns in ProjectMapping:")
for column in first_mapping.__table__.columns:
    print(column.name)
