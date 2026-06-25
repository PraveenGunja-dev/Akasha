import sys
import logging
from database import SessionLocal
from services.p6_service import P6Service

logging.basicConfig(level=logging.INFO)
db = SessionLocal()
p6 = P6Service()

try:
    count = p6.sync_activities_to_db(db, project_object_id=2618)
    print(f"Successfully synced {count} activities for project object ID 2618 (FY25-BANDHA_500MW)")
except Exception as e:
    print(f"Error syncing activities: {e}")
