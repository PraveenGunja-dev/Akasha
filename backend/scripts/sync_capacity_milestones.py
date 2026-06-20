import sys
import os
import json
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

# Setup paths and environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dotenv
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv.load_dotenv(os.path.join(base_dir, '.env'))

from database import SessionLocal
from models import P6Project, ProjectMapping, MTTrialRun
from services.p6_service import P6Service

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Hardcoded Wind Projects as provided
WIND_PROJECTS = {
    # Project ID -> MW per WTG multiplier
    "3074": 5.2, # AGE25CL PSS-11
    "4707": 5.0, # AGE25CL PSS-18 Phase-4
    "3075": 5.2, # AGE26AL PSS-12
    "3076": 5.2, # AHEJ5L PSS-05
    "3072": 5.2, # ARE3L PSS-08
    "3073": 5.2, # ASEJ6PL PSS-08
    "6733": 5.2, # Digital DPR - Demo
    "3105": 3.3, # MANDVI
    "MUNDRA NORTH NEW": 3.3 # Doesn't have an ID in prompt, fallback
}
DEFAULT_WIND_MW = 5.2
DEFAULT_SOLAR_BLOCK_MW = 12.5

def fetch_capacity_milestones():
    logger.info("Starting Capacity Milestones Sync (Daily Job)")
    db = SessionLocal()
    p6 = P6Service()
    
    # 1. Gather Projects
    solar_projects = db.query(ProjectMapping).all()
    # P6 projects mapping
    all_p6 = {str(p.project_id): p for p in db.query(P6Project).all()}
    all_p6_by_name = {str(p.name).lower(): p for p in db.query(P6Project).all()}
    all_p6_by_obj_id = {str(p.p6_object_id): p for p in db.query(P6Project).all()}
    
    projects_to_sync = []
    
    # Add Solar
    for s in solar_projects:
        p6_proj = all_p6.get(str(s.project_id))
        if not p6_proj:
            # try finding by name
            for name, proj in all_p6_by_name.items():
                if str(s.project_id).lower() in name or (s.project_name_from_p6 and s.project_name_from_p6.lower() in name):
                    p6_proj = proj
                    break
        if p6_proj:
            projects_to_sync.append({"type": "Solar", "p6_id": p6_proj.p6_object_id, "name": p6_proj.name, "spv": s.spv_name or ""})
            
    # Add Wind
    for wind_id, mw in WIND_PROJECTS.items():
        p6_proj = all_p6_by_obj_id.get(wind_id)
        if not p6_proj:
            # try name
            p6_proj = all_p6_by_name.get(wind_id.lower())
            
        if p6_proj:
            projects_to_sync.append({"type": "Wind", "p6_id": p6_proj.p6_object_id, "name": p6_proj.name, "mw_multiplier": mw, "spv": ""})
            
    logger.info(f"Identified {len(projects_to_sync)} projects for capacity tracking.")
    
    total_upserts = 0
    
    for proj in projects_to_sync:
        p6_obj_id = proj["p6_id"]
        logger.info(f"Syncing Project: {proj['name']} (ID: {p6_obj_id}) - {proj['type']}")
        
        try:
            # Fetch WBS
            wbs_endpoint = f"{p6.base_url}/wbs?Fields=ObjectId,Code,Name,ParentObjectId&Filter=ProjectObjectId={p6_obj_id}"
            import requests
            proxies = {
                "http": os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "http://cloudproxy.adani.com:8080",
                "https": os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "http://cloudproxy.adani.com:8080"
            }
            res = requests.get(wbs_endpoint, headers=p6.headers, proxies=proxies, verify=False)
            res.raise_for_status()
            wbs_data = res.json()
            wbs_map = {w['ObjectId']: w for w in wbs_data}
            
            # Fetch Activities
            activities = p6.fetch_activities(p6_obj_id)
            
            # Fetch Resource Assignments
            assignments_endpoint = f"{p6.base_url}/resourceAssignment?Fields=ObjectId,ActivityObjectId,ActivityId,ActivityName,ResourceId,ResourceName,ResourceType,PlannedUnits,AtCompletionUnits,ActualUnits&Filter=ProjectObjectId={p6_obj_id} and ResourceType='Material'"
            res = requests.get(assignments_endpoint, headers=p6.headers, proxies=proxies, verify=False)
            res.raise_for_status()
            assignments = res.json()
            res_map = {}
            for a in assignments:
                act_obj = a.get('ActivityObjectId')
                if act_obj not in res_map:
                    res_map[act_obj] = []
                res_map[act_obj].append(a)
                
            # Filter Activities for COD and Trial Run
            milestones = []
            for act in activities:
                name = act.get("Name", "").lower()
                
                is_match = False
                if proj["type"] == "Solar":
                    if "cod" in name or "trial run certificate" in name:
                        is_match = True
                else:
                    if "cod" in name or "trial run" in name:
                        is_match = True
                        
                if is_match:
                    wbs_obj = act.get('WBSObjectId')
                    # Traverse up WBS to find "block" or "wtg"
                    block_name = "Unknown"
                    curr_wbs = wbs_obj
                    while curr_wbs in wbs_map:
                        w_name = wbs_map[curr_wbs].get("Name", "").lower()
                        if "block" in w_name or "wtg" in w_name:
                            block_name = wbs_map[curr_wbs].get("Name")
                            break
                        curr_wbs = wbs_map[curr_wbs].get("ParentObjectId")
                        
                    if block_name == "Unknown":
                        # Try to extract WTG from activity name (e.g. "WTG11-T&C-WTG Trial Run")
                        parts = name.split("-")
                        if "wtg" in parts[0]:
                            block_name = parts[0].upper()
                            
                    act["BlockName"] = block_name
                    act["Assignments"] = res_map.get(act.get("ObjectId"), [])
                    milestones.append(act)
            
            # Calculate MW and Upsert
            for m in milestones:
                # Calculate capacity
                quantity_mw = 0.0
                
                if proj["type"] == "Solar":
                    # Look for MWdc or similar
                    found_mw = False
                    for r in m["Assignments"]:
                        # If resource UOM is MWdc (we can't fetch UOM easily without joining Resource, but we assume it's the largest planned unit or known name)
                        # We will use PlannedUnits. Usually, a solar block module assignment has PlannedUnits ~ 12.5.
                        units = r.get("PlannedUnits", 0)
                        if units > 5 and units < 50: # Safe assumption for MWdc
                            quantity_mw = units
                            found_mw = True
                            break
                    if not found_mw:
                        quantity_mw = DEFAULT_SOLAR_BLOCK_MW
                else:
                    # Wind
                    count = 0.0
                    for r in m["Assignments"]:
                        # Count the number of WTGs
                        units_val = r.get("PlannedUnits", 0)
                        try:
                            count += float(units_val)
                        except (ValueError, TypeError):
                            pass
                    
                    if count == 0:
                        count = 1.0 # Default to 1 WTG
                        
                    quantity_mw = count * proj["mw_multiplier"]
                    
                # Dates
                start_str = m.get("ActualStartDate")
                finish_str = m.get("ActualFinishDate")
                
                # We need actual finish, if not, actual start. If neither, it's not achieved.
                # BUT we might want to track planned dates too? No, user says actual dates to know if generated or not.
                start_dt = datetime.strptime(start_str[:19], "%Y-%m-%dT%H:%M:%S") if start_str else None
                finish_dt = datetime.strptime(finish_str[:19], "%Y-%m-%dT%H:%M:%S") if finish_str else None
                
                act_id = str(m.get("Id"))
                
                # Check DB
                existing = db.query(MTTrialRun).filter(MTTrialRun.activity_id == act_id).first()
                if existing:
                    existing.trial_run_start = start_dt
                    existing.trial_run_finish = finish_dt
                    existing.tr_quantity_mw = quantity_mw
                    existing.project_name_block = m["BlockName"]
                    existing.unit_of_measure = proj["type"]
                else:
                    new_rec = MTTrialRun(
                        activity_id=act_id,
                        activity_name=m.get("Name"),
                        project_name=proj["name"],
                        project_name_p6=proj["name"],
                        project_name_block=m["BlockName"],
                        trial_run_start=start_dt,
                        trial_run_finish=finish_dt,
                        tr_quantity_mw=quantity_mw,
                        spv_plant_code=proj["spv"],
                        unit_of_measure=proj["type"]
                    )
                    db.add(new_rec)
                
                total_upserts += 1
                
            db.commit()
            logger.info(f"Upserted {len(milestones)} milestones for {proj['name']}")
            
        except Exception as e:
            logger.error(f"Failed to sync {proj['name']}: {e}")
            db.rollback()
            
    logger.info(f"Capacity Milestones Sync Complete! Total upserts: {total_upserts}")
    
if __name__ == "__main__":
    fetch_capacity_milestones()
