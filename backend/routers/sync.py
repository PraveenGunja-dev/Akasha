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
def sync_sharepoint_data():
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
        ingest_data()
                
        return {
            "status": "success",
            "message": f"Downloaded and ingested {len(downloaded_files)} files from SharePoint into the Database",
            "files": downloaded_files
        }
    except Exception as e:
        logger.error(f"SharePoint sync failed: {e}")
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

@router.post("/tc/sync")
def sync_tc_data():
    from services.tc_sync import run_sync
    try:
        run_sync()
        return {"status": "success", "message": "Synced Transmission Data"}
    except Exception as e:
        logger.error(f"TC sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"TC sync failed: {str(e)}")

@router.post("/mapping/sync")
def sync_mapping_data():
    from scripts.ingest_mapping import ingest_mapping
    try:
        ingest_mapping()
        return {"status": "success", "message": "Synced Mappings"}
    except Exception as e:
        logger.error(f"Mapping sync failed: {e}")
        raise HTTPException(status_code=500, detail=f"Mapping sync failed: {str(e)}")
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
