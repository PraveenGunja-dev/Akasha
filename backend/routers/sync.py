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
    """SharePoint is the only SAP feed. Every run is written to sync_log so the
    SAP page can show the data's own date, and a failed pull is visible
    instead of leaving yesterday's numbers up with no warning."""
    from datetime import datetime
    from scripts.ingest_sap_data import SAP_DATA_DIR, SAP_FILE_PATTERNS, ingest_data
    import models

    log = models.SyncLog(source="sharepoint", status="running")
    db.add(log); db.commit()

    def finish(status, message, **fields):
        for k, v in fields.items():
            setattr(log, k, v)
        log.status, log.message, log.finished_at = status, message, datetime.utcnow()
        db.commit()

    try:
        sp_service = SharePointService()
        files = sp_service.list_files_in_target_folder()
        # Only the extracts the ingest consumes; the folder also carries CJI3/ZPS021 etc.
        wanted = [f for f in files if f.get("download_url")
                  and any(p.match(f["name"]) for p in SAP_FILE_PATTERNS.values())]
        if not any(SAP_FILE_PATTERNS["zsps"].match(f["name"]) for f in wanted):
            raise RuntimeError(f"ZPSPS007 (PO book of record) not found in {sp_service.target_folder}")

        downloaded = []
        for f in wanted:
            sp_service.download_file(f["download_url"], os.path.join(SAP_DATA_DIR, f["name"]))
            downloaded.append({"name": f["name"], "modified": f.get("modified"), "size_mb": round((f.get("size") or 0) / 1e6, 1)})

        ingest_data()
        # SLR is the same ZPSPS007 extract through its own filters, so it refreshes with it.
        from scripts.ingest_slr_data import ingest_slr
        slr_rows = ingest_slr()
        # Prefix index, filter facets and insights were built on the old tables.
        from routers.sap import _CACHE as sap_cache
        sap_cache.clear()

        # The data date is the newest extract's own modified time, not our clock.
        as_on = max(datetime.fromisoformat(f["modified"].replace("Z", "+00:00")).replace(tzinfo=None)
                    for f in downloaded if f.get("modified"))
        msg = f"Ingested {len(downloaded)} SAP extracts from SharePoint; SLR rebuilt ({slr_rows} rows)"
        finish("success", msg, files=downloaded, data_as_on=as_on)
        return {"status": "success", "message": msg, "folder": sp_service.target_folder,
                "files": downloaded, "data_as_on": as_on.isoformat(), "ingested": True, "slr_rows": slr_rows}
    except Exception as e:
        logger.error(f"SharePoint sync failed: {e}")
        finish("failed", str(e)[:1000])
        raise HTTPException(status_code=500, detail=f"SharePoint sync failed: {str(e)}")

@router.post("/p6/sync")
def sync_p6_data(db: Session = Depends(get_db)):
    p6 = P6Service()
    try:
        result = p6.full_sync(db)
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
def sync_mapping_data():
    from scripts.ingest_mapping import ingest_mapping
    try:
        ingest_mapping()
        return {"status": "success", "message": "Synced Mappings"}
    except Exception as e:
        logger.error(f"Mapping sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Mapping sync failed: {str(e)}")

@router.post("/capacity/sync")
def sync_capacity_data():
    from scripts.sync_capacity_milestones import fetch_capacity_milestones
    try:
        fetch_capacity_milestones()
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
        return {
            "status": "success",
            "message": f"Synced {result['ncs']} NCs and {result['rfis']} RFIs from Pulse",
            **result
        }
    except Exception as e:
        logger.error(f"Pulse sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pulse sync failed: {str(e)}")

@router.post("/einvoice/sync")
def sync_einvoice_data():
    from scripts.sync_einvoice_live import sync_einvoice_live
    try:
        sync_einvoice_live()
        return {"status": "success", "message": "Synced E-Invoice Data"}
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
