import sys
from database import SessionLocal
from engine.intelligence.core import get_project_intelligence

db = SessionLocal()
try:
    print(get_project_intelligence(db, "FY26-P08"))
except Exception as e:
    import traceback
    traceback.print_exc()
