import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

    print("\n🎉 EMERGENCY SETUP COMPLETE!")
    print("⚠️ IMPORTANT: Please completely restart your backend FastAPI server to clear the memory cache and load the new code!")

if __name__ == "__main__":
    run_emergency_setup()
