import requests
import json
import logging
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from database import SessionLocal
from models import TcProjectEntry, TcNetworkEdge, TcNetworkNode, ProjectMapping
from datetime import datetime

logger = logging.getLogger(__name__)

AUTH_URL = "https://powerback-api.unada.in/api/v1/user/login"
BASE_URL = "https://transmission-api-v3.unada.in"
CREDENTIALS = {
    "email": "zaid@unada.io",
    "password": "Demo@123"
}

def get_auth_token():
    try:
        res = requests.post(AUTH_URL, json=CREDENTIALS, verify=False)
        res.raise_for_status()
        data = res.json()
        if "token" in data: return data["token"]
        if "data" in data and "token" in data["data"]: return data["data"]["token"]
        if "access_token" in data: return data["access_token"]
    except Exception as e:
        logger.error(f"Failed to get auth token: {e}")
    return None

def fetch_data(endpoint: str, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(f"{BASE_URL}{endpoint}", headers=headers, verify=False)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            # 404 is expected for unmapped or non-existent projects
            return None
        logger.error(f"Failed to fetch {endpoint}: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch {endpoint}: {e}")
        return None

def normalize_p6_name(name):
    if not name:
        return ""
    clean = str(name).strip().replace(" ", "").lower()
    if clean.endswith("_commissioned"):
        clean = clean[:-13]
    return clean

def find_mapping_id(db: Session, project_names, p6_map=None):
    """Attempt to find a mapping ID using a 2-level strategy (Direct and P6 fallback)"""
    if not project_names:
        return None
        
    names = project_names if isinstance(project_names, list) else [project_names]
    
    all_maps = None
    
    for name in names:
        if not name: continue
        
        # LEVEL 1: Match inside comma-separated database values
        if all_maps is None:
            all_maps = db.query(ProjectMapping).all()
            
        for m in all_maps:
            if m.project:
                tc_names = [t.strip() for t in m.project.split(',')]
                if name in tc_names:
                    return m.id
                
        # LEVEL 2: P6 Name Fallback via p6_map
        if p6_map and name in p6_map:
            norm_p6 = normalize_p6_name(p6_map[name])
                
            for m in all_maps:
                if m.project_name_from_p6 and normalize_p6_name(m.project_name_from_p6) == norm_p6:
                    return m.id
                        
    return None

def get_global_topology(token: str, region: str):
    """Fetches the global snapshot to get accurate node coordinates and edge from/to links"""
    proj_data = fetch_data(f"/api/{region}/projects", token)
    if not proj_data or "projects" not in proj_data:
        logger.error(f"No {region} global projects found")
        return None
        
    current_proj = next((p for p in proj_data["projects"] if p.get("is_current")), None)
    if not current_proj:
        logger.error(f"No current {region} global project found")
        return None
        
    data = fetch_data(f"/api/{region}/projects/{current_proj['id']}", token)
    if not data or "data" not in data or "network" not in data["data"]:
        logger.error(f"Invalid {region} global network data")
        return None
        
    network = data["data"]["network"]
    
    # Map edges by ID to retrieve their topology later
    global_edges = {}
    for e in network.get("edges", []):
        global_edges[e.get("id")] = e
        
    return {
        "nodes": network.get("nodes", []),
        "edges": global_edges
    }

def sync_region_data(db: Session, token: str, region: str):
    logger.info(f"Syncing {region} data...")
    
    # 1. Fetch Global Topology (Provides nodes, and from/to for edges)
    topology = get_global_topology(token, region.lower())
    if not topology:
        return
        
    # Get existing edges to track status changes (for notifications)
    existing_edges = {e.edge_id: e.status for e in db.query(TcNetworkEdge).filter(TcNetworkEdge.region == region).all()}
    
    # Clear region data for full reload
    db.query(TcNetworkEdge).filter(TcNetworkEdge.region == region).delete()
    db.query(TcNetworkNode).filter(TcNetworkNode.region == region).delete()
    db.query(TcProjectEntry).filter(TcProjectEntry.region == region).delete()
    
    # Insert unique global nodes
    for n in topology["nodes"]:
        node = TcNetworkNode(
            region=region,
            node_id=n.get("id"),
            label=n.get("label"),
            type=n.get("type"),
            status=n.get("status"),
            x=n.get("x"),
            y=n.get("y")
        )
        db.add(node)
        
    # 2. Iterate over all mapped projects for precise Edge and Block mapping
    mappings = db.query(ProjectMapping).filter(ProjectMapping.project_id.isnot(None)).all()
    
    for pm in mappings:
        pid = pm.project_id
        if not pid: continue
        
        # Targeted project API Call
        p_data = fetch_data(f"/api/{region.lower()}/project-details?project_id={pid}", token)
        if not p_data:
            continue
            
        # Insert precisely mapped project entries (blocks)
        metadata = p_data.get("metadata", {})
        all_entries = metadata.get("rows", [])
        
        for entry in all_entries:
            pe = TcProjectEntry(
                region=region,
                project=entry.get("project"),
                phase=entry.get("phase"),
                kps=entry.get("kps"),
                pss=entry.get("pss"),
                block=entry.get("block"),
                breakup=str(entry.get("breakup")),
                mw=str(entry.get("mw")),
                mapping_id=pm.id
            )
            db.add(pe)
            
        # Insert precisely mapped edges (lines), utilizing global topology for from/to
        lines = p_data.get("lines", [])
        for e in lines:
            edge_id = e.get("id")
            
            # Lookup topology from global fetch
            global_edge = topology["edges"].get(edge_id, {})
            
            new_status = e.get("status")
            old_status = existing_edges.get(edge_id)
            if old_status and old_status != new_status:
                from models import Notification
                notif = Notification(
                    project_name=pm.project,
                    module="Transmission",
                    change_type="Status Update",
                    message=f"Transmission line '{e.get('from_label')} to {e.get('to_label')}' status updated from '{old_status}' to '{new_status}'"
                )
                db.add(notif)
                
            edge = TcNetworkEdge(
                region=region,
                edge_id=edge_id,
                from_node=global_edge.get("from"),
                from_label=e.get("from_label"),
                to_node=global_edge.get("to"),
                to_label=e.get("to_label"),
                projects=json.dumps({"projects": global_edge.get("project", []), "phases": global_edge.get("phases", [])}),
                contractor=e.get("contractor"),
                voltage=e.get("voltage"),
                length=str(e.get("length") or global_edge.get("length")),
                status=new_status,
                normalized_status=e.get("normalized_status"),
                erection=e.get("erection"),
                foundation=e.get("foundation"),
                stringing=e.get("stringing"),
                expected_date=e.get("expected_date"),
                mapping_id=pm.id
            )
            db.add(edge)
            
    db.commit()
    logger.info(f"Synced {region} Data")

def run_sync():
    logger.info("Starting Transmission Data Sync...")
    token = get_auth_token()
    if not token:
        logger.error("Sync aborted: No auth token.")
        return

    db = SessionLocal()
    try:
        sync_region_data(db, token, "Khavda")
        sync_region_data(db, token, "Rajasthan")
        logger.info("Transmission Data Sync Complete!")
    except Exception as e:
        logger.error(f"Error during sync: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_sync()
