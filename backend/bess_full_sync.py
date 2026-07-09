import logging
from database import SessionLocal
from services.p6_service import P6Service
import models

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_bess_full_sync():
    db = SessionLocal()
    p6 = P6Service()
    try:
        logger.info("Starting full P6 sync for BESS projects...")
        
        # 1. Find BESS projects
        bess_mappings = db.query(models.ProjectMapping).filter(
            models.ProjectMapping.cluster.ilike("%BESS%")
        ).all()
        
        bess_project_ids = [m.project_id for m in bess_mappings if m.project_id]
        logger.info(f"Found {len(bess_project_ids)} BESS projects in mapping.")
        
        # 2. Get P6 Object IDs
        bess_p6_projects = db.query(models.P6Project).filter(
            models.P6Project.project_id.in_(bess_project_ids)
        ).all()
        
        logger.info(f"Found {len(bess_p6_projects)} corresponding P6 projects in database.")
        
        for proj in bess_p6_projects:
            logger.info(f"--- Syncing details for BESS Project: {proj.name} (ObjectID: {proj.p6_object_id}) ---")
            
            wbs_count = p6.sync_wbs_to_db(db, proj.p6_object_id)
            logger.info(f"Synced {wbs_count} WBS elements.")
            
            activities_count = p6.sync_activities_to_db(db, proj.p6_object_id)
            logger.info(f"Synced {activities_count} activities.")
            
            p6.sync_resource_assignments_to_db(db, proj.p6_object_id)
            logger.info("Synced resource assignments.")
            
            risks_count = p6.sync_activity_risks_to_db(db, proj.p6_object_id)
            logger.info(f"Synced {risks_count} activity risks.")
            
        logger.info("BESS Full Sync Completed Successfully!")
        
    except Exception as e:
        logger.error(f"Error during BESS full sync: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_bess_full_sync()
