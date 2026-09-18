from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import os
import logging
from database import get_db
from services.p6_service import P6Service
from services.sharepoint_service import SharePointService

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

@router.post("/sharepoint/sync")
def sync_sharepoint_data(db: Session = Depends(get_db)):
    """SharePoint is the only SAP feed. See services/sap_sync.py."""
    from services.sap_sync import sync_sap_from_sharepoint
    try:
        return sync_sap_from_sharepoint(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SharePoint sync failed: {str(e)}")

@router.post("/p6/sync")
def sync_p6_data(db: Session = Depends(get_db)):
    from services.sync_log_util import run_logged
    p6 = P6Service()
    def _do():
        result = p6.full_sync(db)
        return {
            "status": "success",
            "message": f"Synced {result['projects_synced']} projects and {result['baselines_synced']} baselines",
            **result
        }
    try:
        return run_logged(db, "p6", _do)
    except Exception as e:
        logger.error(f"P6 sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"P6 sync failed: {str(e)}")

@router.post("/p6/sync/{project_object_id}")
def sync_individual_p6_data(project_object_id: int, db: Session = Depends(get_db)):
    p6 = P6Service()
    try:
        result = p6.individual_sync(db, project_object_id)
        return {
            "status": "success",
            "message": f"Synced project {project_object_id}",
            **result
        }
    except Exception as e:
        logger.error(f"P6 individual sync failed for project {project_object_id}: {e}")
        raise HTTPException(status_code=500, detail=f"P6 individual sync failed: {str(e)}")

@router.post("/tc/sync")
def sync_tc_data():
    from services.tc_sync import run_sync
    import threading
    threading.Thread(target=run_sync).start()
    return {"status": "success", "message": "Transmission Data Sync started in background."}

@router.post("/tc/sync/{project_id}")
def sync_tc_project(project_id: str):
    """Synchronous, single-project transmission sync - used by the per-project
    Sync button so the page reload it triggers actually reflects fresh data."""
    from services.tc_sync import sync_single_project
    try:
        result = sync_single_project(project_id)
        return {"status": "success", "message": f"Synced transmission data for {project_id}", **result}
    except Exception as e:
        logger.error(f"TC project sync failed for {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Transmission sync failed: {str(e)}")

@router.post("/mapping/sync")
def sync_mapping_data(db: Session = Depends(get_db)):
    from scripts.ingest_mapping import ingest_mapping
    from services.sync_log_util import run_logged
    try:
        return run_logged(db, "mapping", lambda: (ingest_mapping(), {"status": "success", "message": "Synced Mappings"})[1])
    except Exception as e:
        logger.error(f"Mapping sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Mapping sync failed: {str(e)}")

@router.post("/capacity/sync")
def sync_capacity_data(db: Session = Depends(get_db)):
    from scripts.sync_capacity_milestones import fetch_capacity_milestones
    from services.sync_log_util import run_logged
    try:
        return run_logged(db, "capacity", lambda: (fetch_capacity_milestones(), {"status": "success", "message": "Synced Capacity Milestones"})[1])
    except Exception as e:
        logger.error(f"Capacity sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Capacity sync failed: {str(e)}")

@router.post("/pulse/sync")
def sync_pulse_data(db: Session = Depends(get_db)):
    """Sync Non-Conformances and RFIs from Pulse quality system."""
    from services.pulse_service import PulseService
    from services.sync_log_util import run_logged
    service = PulseService()
    def _do():
        result = service.full_sync(db)
        return {
            "status": "success",
            "message": f"Synced {result['ncs']} NCs and {result['rfis']} RFIs from Pulse",
            **result
        }
    try:
        return run_logged(db, "pulse", _do)
    except Exception as e:
        logger.error(f"Pulse sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pulse sync failed: {str(e)}")

@router.post("/einvoice/sync")
def sync_einvoice_data(db: Session = Depends(get_db)):
    from scripts.sync_einvoice_live import sync_einvoice_live
    from services.sync_log_util import run_logged
    try:
        return run_logged(db, "einvoice", lambda: (sync_einvoice_live(), {"status": "success", "message": "Synced E-Invoice Data"})[1])
    except Exception as e:
        logger.error(f"E-Invoice sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"E-Invoice sync failed: {str(e)}")


import base64
from datetime import datetime
import dotenv
from pydantic import BaseModel

class PasswordUpdate(BaseModel):
    new_password: str

@router.get("/p6/config-status")
def get_p6_config_status():
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    env_dict = dotenv.dotenv_values(env_path)
    last_updated_str = env_dict.get("ORACLE_P6_PASSWORD_LAST_UPDATED", "")
    
    if not last_updated_str:
        return {"days_remaining": 0, "is_expiring_soon": True, "last_updated": None}

    try:
        last_updated = datetime.strptime(last_updated_str, "%Y-%m-%d")
        days_passed = (datetime.utcnow() - last_updated).days
        days_remaining = 45 - days_passed
        is_expiring_soon = days_remaining <= 7
        return {
            "days_remaining": days_remaining,
            "is_expiring_soon": is_expiring_soon,
            "last_updated": last_updated_str
        }
    except ValueError:
        return {"days_remaining": 0, "is_expiring_soon": True, "last_updated": last_updated_str}

@router.post("/p6/update-password")
def update_p6_password(data: PasswordUpdate):
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    env_dict = dotenv.dotenv_values(env_path)
    old_token_b64 = env_dict.get("ORACLE_P6_OAUTH_TOKEN", "")
    
    username = "agel.forecasting@adani.com"
    if old_token_b64:
        try:
            decoded = base64.b64decode(old_token_b64).decode('utf-8')
            if ":" in decoded:
                username = decoded.split(":")[0]
        except Exception as e:
            logger.warning(f"Could not decode old token: {e}")
            
    new_raw = f"{username}:{data.new_password}"
    new_token_b64 = base64.b64encode(new_raw.encode('utf-8')).decode('utf-8')
    
    dotenv.set_key(env_path, "ORACLE_P6_OAUTH_TOKEN", new_token_b64)
    dotenv.set_key(env_path, "ORACLE_P6_AUTH_TOKEN", new_token_b64)
    
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    dotenv.set_key(env_path, "ORACLE_P6_PASSWORD_LAST_UPDATED", today_str)
    
    os.environ["ORACLE_P6_OAUTH_TOKEN"] = new_token_b64
    os.environ["ORACLE_P6_AUTH_TOKEN"] = new_token_b64
    os.environ["ORACLE_P6_PASSWORD_LAST_UPDATED"] = today_str
    
    return {"status": "success", "message": "P6 password updated successfully"}
