from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session
import os
import logging
from database import get_db
import models
from services.p6_service import P6Service
from services.sharepoint_service import SharePointService
from services.freshness_service import mark_source_sync_succeeded

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _latest_p6_data_as_of(db: Session):
    return db.query(func.max(models.P6Project.data_date)).scalar()


def _latest_pulse_data_as_of(db: Session):
    cutoffs = (
        db.query(func.max(models.PulseNC.updated_at)).scalar(),
        db.query(func.max(models.PulseRFI.updated_at)).scalar(),
    )
    return max((value for value in cutoffs if value is not None), default=None)


def _latest_sap_data_as_of(db: Session):
    cutoffs = (
        db.query(func.max(models.MTPOAmount.document_date)).scalar(),
        db.query(func.max(models.MTInventory.posting_date)).scalar(),
        db.query(func.max(models.MTMaterialDocument.posting_date)).scalar(),
    )
    return max((value for value in cutoffs if value is not None), default=None)


def _clear_p6_caches():
    from routers.dashboard import clear_dashboard_caches
    from routers.pmag import clear_pmag_caches
    from routers.projects import clear_project_caches
    clear_dashboard_caches()
    clear_pmag_caches()
    clear_project_caches()


def _clear_all_operational_caches(db: Session):
    from engine.cache import invalidate_cache
    from routers.dashboard import clear_dashboard_caches
    from routers.financials import clear_financial_cache
    from routers.logistics import clear_logistics_cache
    from routers.pmag import clear_pmag_caches
    from routers.projects import clear_project_caches

    invalidate_cache(db)
    clear_dashboard_caches()
    clear_pmag_caches()
    clear_project_caches()
    clear_financial_cache()
    clear_logistics_cache()

@router.post("/sharepoint/sync")
def sync_sharepoint_data(db: Session = Depends(get_db)):
    sp_service = SharePointService()
    try:
        files = sp_service.list_files_in_target_folder()
        if not files:
            return {"status": "success", "message": "No files found to sync today.", "files": []}
            
        download_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "downloads")
        os.makedirs(download_dir, exist_ok=True)
        
        downloaded_files = []
        for f in files:
            if f.get("download_url"):
                save_path = os.path.join(download_dir, f["name"])
                sp_service.download_file(f["download_url"], save_path)
                downloaded_files.append(f["name"])
                
        from scripts.ingest_sap_data import ingest_data
        
        # Run database ingestion
        ingestion = ingest_data()
        if not ingestion.get("success"):
            raise RuntimeError("SAP ingestion incomplete: " + "; ".join(ingestion.get("errors", [])))
        mark_source_sync_succeeded(db, "SAP", data_as_of=_latest_sap_data_as_of(db))
        _clear_all_operational_caches(db)
                
        return {
            "status": "success",
            "message": f"Downloaded and ingested {len(downloaded_files)} files from SharePoint into the Database",
            "files": downloaded_files,
            "ingestion": ingestion,
        }
    except Exception as e:
        logger.error(f"SharePoint sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"SharePoint sync failed: {str(e)}")

@router.post("/p6/sync")
def sync_p6_data(db: Session = Depends(get_db)):
    p6 = P6Service()
    try:
        result = p6.full_sync(db)
        mark_source_sync_succeeded(db, "P6", data_as_of=_latest_p6_data_as_of(db))
        _clear_p6_caches()
        return {
            "status": "success",
            "message": f"Synced {result['projects_synced']} projects and {result['baselines_synced']} baselines",
            **result
        }
    except Exception as e:
        logger.error(f"P6 sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"P6 sync failed: {str(e)}")

@router.post("/p6/sync/{project_object_id}")
def sync_individual_p6_data(project_object_id: int, db: Session = Depends(get_db)):
    p6 = P6Service()
    try:
        result = p6.individual_sync(db, project_object_id)
        mark_source_sync_succeeded(db, "P6", data_as_of=_latest_p6_data_as_of(db))
        _clear_p6_caches()
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

@router.post("/mapping/sync")
def sync_mapping_data(db: Session = Depends(get_db)):
    from scripts.ingest_mapping import ingest_mapping
    try:
        ingestion = ingest_mapping(db=db)
        mark_source_sync_succeeded(db, "Mapping")
        _clear_all_operational_caches(db)
        return {
            "status": "success",
            "message": "Synced Mappings",
            "ingestion": ingestion,
        }
    except Exception as e:
        logger.error(f"Mapping sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Mapping sync failed: {str(e)}")

@router.post("/capacity/sync")
def sync_capacity_data(db: Session = Depends(get_db)):
    from scripts.sync_capacity_milestones import fetch_capacity_milestones
    try:
        fetch_capacity_milestones()
        mark_source_sync_succeeded(db, "Capacity", data_as_of=_latest_p6_data_as_of(db))
        _clear_all_operational_caches(db)
        return {"status": "success", "message": "Synced Capacity Milestones"}
    except Exception as e:
        logger.error(f"Capacity sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Capacity sync failed: {str(e)}")

@router.post("/pulse/sync")
def sync_pulse_data(db: Session = Depends(get_db)):
    """Sync Non-Conformances and RFIs from Pulse quality system."""
    from services.pulse_service import PulseService
    try:
        service = PulseService()
        result = service.full_sync(db)
        mark_source_sync_succeeded(db, "Pulse", data_as_of=_latest_pulse_data_as_of(db))
        _clear_all_operational_caches(db)
        return {
            "status": "success",
            "message": f"Synced {result['ncs']} NCs and {result['rfis']} RFIs from Pulse",
            **result
        }
    except Exception as e:
        logger.error(f"Pulse sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pulse sync failed: {str(e)}")

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
