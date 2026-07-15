import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from database import SessionLocal
from routers.dashboard import get_capacity_overview

db = SessionLocal()
cap_data = get_capacity_overview(None, db)
print("totals:", cap_data.get("totals"))
print("sum:", sum(cap_data.get("totals", {}).values()))
