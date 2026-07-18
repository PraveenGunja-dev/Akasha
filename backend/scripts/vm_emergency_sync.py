import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from database import engine, SessionLocal
import models
from services.pulse_service import PulseService

def run_emergency_setup():
    print("🚀 Running VM Emergency Setup & Migration...")
    
    # 1. Create missing tables directly without Alembic
    print("🛠️ Creating missing tables in the database (Bypassing Alembic)...")
    try:
        models.Base.metadata.create_all(bind=engine)
        print("✅ Tables created/verified successfully!")
    except Exception as e:
        print(f"❌ Error creating tables: {e}")
        return
        
    print("🛠️ Injecting new labor unit columns into p6_project table...")
    try:
        with engine.connect() as conn:
            from sqlalchemy import text
            conn.execute(text("ALTER TABLE p6_project ADD COLUMN IF NOT EXISTS baseline_non_labor_units FLOAT;"))
            conn.execute(text("ALTER TABLE p6_project ADD COLUMN IF NOT EXISTS actual_non_labor_units FLOAT;"))
            conn.execute(text("ALTER TABLE p6_project ADD COLUMN IF NOT EXISTS budget_labor_units FLOAT;"))
            conn.execute(text("ALTER TABLE p6_project ADD COLUMN IF NOT EXISTS at_completion_non_labor_units FLOAT;"))
            conn.commit()
            print("✅ Columns added successfully!")
    except Exception as e:
        print(f"⚠️ Columns likely already exist (skipping): {e}")

    # 1.5 Clean up previously injected dummy PULSE projects
    print("🧹 Cleaning up dummy PULSE projects injected from previous sync...")
    db = SessionLocal()
    try:
        deleted = db.query(models.ProjectMapping).filter(models.ProjectMapping.project_id.like("PULSE-%")).delete(synchronize_session=False)
        db.commit()
        print(f"✅ Deleted {deleted} dummy PULSE projects from ProjectMapping!")
    except Exception as e:
        print(f"❌ Error cleaning up PULSE projects: {e}")
    finally:
        db.close()

    # 2. Run Pulse Sync to fetch missing projects
    print("🔄 Running Pulse Sync to fetch NCs/RFIs and add missing projects...")
    db = SessionLocal()
    try:
        pulse = PulseService()
        result = pulse.full_sync(db)
        print(f"✅ Pulse Sync Complete! Synced {result.get('ncs', 0)} NCs, {result.get('rfis', 0)} RFIs.")
        print(f"✅ Injected {result.get('new_projects', 0)} NEW Pulse Projects into ProjectMapping!")
    except Exception as e:
        print(f"❌ Error during Pulse Sync: {e}")
    finally:
        db.close()

    # 3. Sync Transmission (TC) Data
    print("⚡ Syncing Transmission Network (TC) Data...")
    try:
        from services.tc_sync import run_sync
        run_sync()
        print("✅ Transmission Data Sync Complete!")
    except Exception as e:
        print(f"❌ Error during Transmission Sync: {e}")

    print("\n🎉 EMERGENCY SETUP COMPLETE!")
    print("⚠️ IMPORTANT: Please completely restart your backend FastAPI server to clear the memory cache and load the new code!")

if __name__ == "__main__":
    run_emergency_setup()
