from database import SessionLocal
from services.project_service import calculate_project_360_metrics

db = SessionLocal()
try:
    print("Testing calculate_project_360_metrics...")
    calculate_project_360_metrics(db)
    print("Success!")
except Exception as e:
    import traceback
    traceback.print_exc()
finally:
    db.close()
