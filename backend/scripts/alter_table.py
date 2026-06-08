import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    db.execute(text("ALTER TABLE project_mapping ADD COLUMN tc_project_name VARCHAR;"))
    db.commit()
    print("Column added successfully!")
except Exception as e:
    print(f"Error adding column: {e}")
finally:
    db.close()
