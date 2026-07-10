import logging
from database import SessionLocal
from services.p6_service import P6Service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_fast_sync():
    db = SessionLocal()
    p6 = P6Service()
    try:
        logger.info("Starting fast P6 sync (Projects and Baselines only)...")
        projects_synced = p6.sync_projects_to_db(db)
        logger.info(f"Successfully synced {projects_synced} projects from P6.")
        
        baselines_synced = p6.sync_baselines_to_db(db)
        logger.info(f"Successfully synced {baselines_synced} baselines from P6.")
        
    except Exception as e:
        logger.error(f"Error during fast sync: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_fast_sync()
