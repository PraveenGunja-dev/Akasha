import sys
from database import SessionLocal
from routers.dashboard import get_dashboard_summary

db = SessionLocal()
try:
    res = get_dashboard_summary(db=db)
    print("Success, returned", len(res["projects"]), "projects")
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
