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
        res = requests.post(AUTH_URL, json=CREDENTIALS)
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
        res = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
        res.raise_for_status()
        return res.json()
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

def find_mapping_id(db: Session, project_names, edge_data=None):
    """Attempt to find a mapping ID using a 3-level strategy"""
    if not project_names:
        return None
        
    names = project_names if isinstance(project_names, list) else [project_names]
    
    ALIAS_MAP = {
        "MLP T1  PPA - J&K": "MLP T1 J&K",
        "MLP T1  PPA - CG": "MLP T1 CG",
        "MLP T1  PPA - TN": "MLP T1 TN",
        "MLP T1  PPA - OR": "MLP T1 OR",
        "MLP T3 PPA - AP": "MLP T3 AP",
        "MLP  PPA - AP New": "MLP AP New",
        "Group - Cement (Hybrid - Solar)": "ACL",
        "AGEL Hybrid Merchant (Wind)": "AGEL Hybrid Merchant"
    }
    
    # Cache mappings for level 3 to avoid N+1 queries
    all_maps = None
    
    for name in names:
        if not name: continue
        
        # LEVEL 1: Exact Match
        mapping = db.query(ProjectMapping).filter(ProjectMapping.project == name).first()
        if mapping:
            return mapping.id
            
        # LEVEL 2: Alias Lookup
        if name in ALIAS_MAP:
            target = ALIAS_MAP[name]
            q = db.query(ProjectMapping).filter(ProjectMapping.project == target)
            if target == "ACL":
                q = q.filter(ProjectMapping.spv_name == "ACL")
            mapping = q.first()
            if mapping:
                return mapping.id
                
        # LEVEL 3: P6 Name Fallback via table5Entries
        if edge_data and "table5Entries" in edge_data:
            entries = edge_data["table5Entries"]
            for entry in entries:
                p6_val = entry.get("p6project")
                if not p6_val:
                    continue
                norm_p6 = normalize_p6_name(p6_val)
                
                if all_maps is None:
                    all_maps = db.query(ProjectMapping).all()
                    
                for m in all_maps:
                    if m.project_name_from_p6 and normalize_p6_name(m.project_name_from_p6) == norm_p6:
                        return m.id
                        
    return None

def sync_khavda_data(db: Session, token: str):
    # 1. Get projects list
    proj_data = fetch_data("/api/khavda/projects", token)
    if not proj_data or "projects" not in proj_data:
        logger.error("No khavda projects found")
        return
        
    current_proj = next((p for p in proj_data["projects"] if p.get("is_current")), None)
    if not current_proj:
        logger.error("No current khavda project found")
        return
        
    proj_id = current_proj["id"]
    logger.info(f"Fetching Khavda snapshot: {proj_id}")
    
    # 2. Get data for the current project
    data = fetch_data(f"/api/khavda/projects/{proj_id}", token)
    if not data or "data" not in data or "network" not in data["data"]:
        logger.error("Invalid Khavda network data")
        return
        
    db.query(TcNetworkEdge).filter(TcNetworkEdge.region == "Khavda").delete()
    db.query(TcNetworkNode).filter(TcNetworkNode.region == "Khavda").delete()
    db.query(TcProjectEntry).filter(TcProjectEntry.region == "Khavda").delete()
    
    filters = data["data"].get("filters", {})
    table5 = filters.get("table5Entries", [])
    projectEntries = filters.get("projectEntries", [])
    all_entries = table5 if len(table5) > 0 else projectEntries
    
    for entry in all_entries:
        project_name = entry.get("project")
        if not project_name: continue
        
        # Mock edge_data structure for find_mapping_id Level 3 fallback
        mock_edge = {"table5Entries": [entry]}
        mapping_id = find_mapping_id(db, [project_name], edge_data=mock_edge)
        
        pe = TcProjectEntry(
            region="Khavda",
            project=project_name,
            phase=entry.get("phase"),
            kps=entry.get("kps"),
            pss=entry.get("pss"),
            block=entry.get("block"),
            breakup=str(entry.get("breakup")),
            mw=str(entry.get("mw")),
            mapping_id=mapping_id
        )
        db.add(pe)
        
    network = data["data"]["network"]
    
    for n in network.get("nodes", []):
        node = TcNetworkNode(
            region="Khavda",
            node_id=n.get("id"),
            label=n.get("label"),
            type=n.get("type"),
            status=n.get("status"),
            x=n.get("x"),
            y=n.get("y")
        )
        db.add(node)
        
    for e in network.get("edges", []):
        projects = e.get("project", [])
        mapping_id = find_mapping_id(db, projects, edge_data=e)
        
        edge = TcNetworkEdge(
            region="Khavda",
            edge_id=e.get("id"),
            from_node=e.get("from"),
            from_label=e.get("from_label"),
            to_node=e.get("to"),
            to_label=e.get("to_label"),
            projects=json.dumps(projects),
            contractor=e.get("contractor"),
            voltage=e.get("voltage"),
            length=str(e.get("length")),
            status=e.get("status"),
            normalized_status=e.get("normalized_status"),
            erection=e.get("erection"),
            foundation=e.get("foundation"),
            stringing=e.get("stringing"),
            expected_date=e.get("expected_date"),
            mapping_id=mapping_id
        )
        db.add(edge)

    db.commit()
    logger.info("Synced Khavda Data")

def sync_rajasthan_data(db: Session, token: str):
    # 1. Get projects list
    proj_data = fetch_data("/api/rajasthan/projects", token)
    if not proj_data or "projects" not in proj_data:
        logger.error("No rajasthan projects found")
        return
        
    current_proj = next((p for p in proj_data["projects"] if p.get("is_current")), None)
    if not current_proj:
        logger.error("No current rajasthan project found")
        return
        
    proj_id = current_proj["id"]
    logger.info(f"Fetching Rajasthan snapshot: {proj_id}")
    
    # 2. Get data for the current project
    data = fetch_data(f"/api/rajasthan/projects/{proj_id}", token)
    if not data or "data" not in data or "network" not in data["data"]:
        logger.error("Invalid Rajasthan network data")
        return
        
    db.query(TcNetworkEdge).filter(TcNetworkEdge.region == "Rajasthan").delete()
    db.query(TcNetworkNode).filter(TcNetworkNode.region == "Rajasthan").delete()
    db.query(TcProjectEntry).filter(TcProjectEntry.region == "Rajasthan").delete()
    
    filters = data["data"].get("filters", {})
    table5 = filters.get("table5Entries", [])
    projectEntries = filters.get("projectEntries", [])
    all_entries = table5 if len(table5) > 0 else projectEntries
    
    for entry in all_entries:
        project_name = entry.get("project")
        if not project_name: continue
        
        mock_edge = {"table5Entries": [entry]}
        mapping_id = find_mapping_id(db, [project_name], edge_data=mock_edge)
        
        pe = TcProjectEntry(
            region="Rajasthan",
            project=project_name,
            phase=entry.get("phase"),
            kps=entry.get("kps"),
            pss=entry.get("pss"),
            block=entry.get("block"),
            breakup=str(entry.get("breakup")),
            mw=str(entry.get("mw")),
            mapping_id=mapping_id
        )
        db.add(pe)
        
    network = data["data"]["network"]
    
    for n in network.get("nodes", []):
        node = TcNetworkNode(
            region="Rajasthan",
            node_id=n.get("id"),
            label=n.get("label"),
            type=n.get("type"),
            status=n.get("status"),
            x=n.get("x"),
            y=n.get("y")
        )
        db.add(node)
        
    for e in network.get("edges", []):
        projects = e.get("project", [])
        mapping_id = find_mapping_id(db, projects, edge_data=e)
        
        edge = TcNetworkEdge(
            region="Rajasthan",
            edge_id=e.get("id"),
            from_node=e.get("from"),
            from_label=e.get("from_label"),
            to_node=e.get("to"),
            to_label=e.get("to_label"),
            projects=json.dumps(projects),
            contractor=e.get("contractor"),
            voltage=e.get("voltage"),
            length=str(e.get("length")),
            status=e.get("status"),
            normalized_status=e.get("normalized_status"),
            erection=e.get("erection"),
            foundation=e.get("foundation"),
            stringing=e.get("stringing"),
            expected_date=e.get("expected_date"),
            mapping_id=mapping_id
        )
        db.add(edge)

    db.commit()
    logger.info("Synced Rajasthan Data")

def run_sync():
    logger.info("Starting Transmission Data Sync...")
    token = get_auth_token()
    if not token:
        logger.error("Sync aborted: No auth token.")
        return

    db = SessionLocal()
    try:
        sync_khavda_data(db, token)
        sync_rajasthan_data(db, token)
        logger.info("Transmission Data Sync Complete!")
    except Exception as e:
        logger.error(f"Error during sync: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_sync()
