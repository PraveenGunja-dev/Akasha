import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from routers.project_360 import get_project_360_detail
from fastapi import HTTPException

db = SessionLocal()
try:
    detail = get_project_360_detail("FY26-P20", db)
    mapping = detail.get("p6", {}).get("mapping", {})
    print("Mapping Info:", mapping)
except Exception as e:
    print(e)
