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

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class TcSyncError(RuntimeError):
    """Raised when the transmission source cannot complete a sync."""

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
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            # 404 is expected for unmapped or non-existent projects
            return None
        logger.error(f"Failed to fetch {endpoint}: {e}")
        raise TcSyncError(f"Failed to fetch TC endpoint {endpoint}") from e
    except Exception as e:
        logger.error(f"Failed to fetch {endpoint}: {e}")
        raise TcSyncError(f"Failed to fetch TC endpoint {endpoint}") from e


def get_global_topology(token: str, region: str):
    """Fetches the global snapshot to get accurate node coordinates and edge from/to links"""
    proj_data = fetch_data(f"/api/{region}/projects", token)
    if not proj_data or "projects" not in proj_data:
        raise TcSyncError(f"No valid {region} global projects response")
        
    current_proj = next((p for p in proj_data["projects"] if p.get("is_current")), None)
    if not current_proj:
        raise TcSyncError(f"No current {region} global project found")
        
    data = fetch_data(f"/api/{region}/projects/{current_proj['id']}", token)
    if not data or "data" not in data or "network" not in data["data"]:
        raise TcSyncError(f"Invalid {region} global network data")
        
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
        
    existing_nodes = {n.node_id: n for n in db.query(TcNetworkNode).filter(TcNetworkNode.region == region).all()}
    
    # Upsert unique global nodes
    for n in topology["nodes"]:
        n_id = n.get("id")
        if n_id in existing_nodes:
            node = existing_nodes[n_id]
            node.label = n.get("label")
            node.type = n.get("type")
            node.status = n.get("status")
            node.x = n.get("x")
            node.y = n.get("y")
        else:
            node = TcNetworkNode(
                region=region,
                node_id=n_id,
                label=n.get("label"),
                type=n.get("type"),
                status=n.get("status"),
                x=n.get("x"),
                y=n.get("y")
            )
            db.add(node)
            
    existing_entries = {(pe.mapping_id, pe.block): pe for pe in db.query(TcProjectEntry).filter(TcProjectEntry.region == region).all()}
    existing_edges = {(e.mapping_id, e.edge_id): e for e in db.query(TcNetworkEdge).filter(TcNetworkEdge.region == region).all()}
    
    seen_entry_keys = set()
    seen_edge_keys = set()
        
    # 2. Iterate over all mapped projects for precise Edge and Block mapping
    mappings = db.query(ProjectMapping).filter(ProjectMapping.project_id.isnot(None)).all()
    
    from models import Notification

    for pm in mappings:
        pid = pm.project_id
        if not pid: continue
        
        # Targeted project API Call
        p_data = fetch_data(f"/api/{region.lower()}/project-details?project_id={pid}", token)

        RAJ_EXTERNAL_MAP = {
            "FY25-BANDHA_500MW": "Siyambar"
        }

        # Fallback for Rajasthan if project-details is missing
        if not p_data and region.lower() == 'rajasthan' and pid in RAJ_EXTERNAL_MAP:
            siyambar_key = RAJ_EXTERNAL_MAP[pid]
            matched_lines = []
            for global_e in topology["edges"].values():
                proj_list = global_e.get("project", [])
                if any(siyambar_key in p for p in proj_list):
                    matched_lines.append(global_e)
            
            if matched_lines:
                p_data = {
                    "progress": {},
                    "metadata": {"rows": []},
                    "lines": matched_lines
                }

        if not p_data:
            continue
            
        # Insert precisely mapped project entries (blocks)
        metadata = p_data.get("metadata", {})
        all_entries = metadata.get("rows", [])
        
        # Save rich progress metrics natively to the DB
        pm.tc_progress = p_data.get("progress", {})
        
        for entry in all_entries:
            block = entry.get("block")
            key = (pm.id, block)
            seen_entry_keys.add(key)
            if key in existing_entries:
                pe = existing_entries[key]
                pe.project = entry.get("project")
                pe.phase = entry.get("phase")
                pe.kps = entry.get("kps")
                pe.pss = entry.get("pss")
                pe.breakup = str(entry.get("breakup"))
                pe.mw = str(entry.get("mw"))
            else:
                pe = TcProjectEntry(
                    region=region,
                    project=entry.get("project"),
                    phase=entry.get("phase"),
                    kps=entry.get("kps"),
                    pss=entry.get("pss"),
                    block=block,
                    breakup=str(entry.get("breakup")),
                    mw=str(entry.get("mw")),
                    mapping_id=pm.id
                )
                db.add(pe)
            
        # Insert precisely mapped edges (lines), utilizing global topology for from/to
        lines = p_data.get("lines", [])
        
        for e in lines:
            edge_id = e.get("id")
            key = (pm.id, edge_id)
            seen_edge_keys.add(key)
            
            # Lookup topology from global fetch
            global_edge = topology["edges"].get(edge_id, {})
            
            new_status = e.get("status")
            new_date = e.get("expected_date")
            new_contractor = e.get("contractor")
            
            if key in existing_edges:
                edge = existing_edges[key]
                
                is_currently_delayed = e.get("is_delayed", False)
                is_in_progress = e.get("normalized_status") == 'in_progress'

                if edge.status and edge.status != new_status:
                    db.add(Notification(
                        project_name=pm.project,
                        module="Transmission",
                        change_type="Status Update",
                        message=f"Line '{e.get('from_label')} to {e.get('to_label')}' status changed from '{edge.status}' to '{new_status}'",
                        category="Dates"
                    ))
                if edge.expected_date and edge.expected_date != new_date:
                    if is_currently_delayed and is_in_progress:
                        db.add(Notification(
                            project_name=pm.project,
                            module="Transmission",
                            change_type="COD Delay",
                            message=f"Transmission Delay Warning: Line '{e.get('from_label')} to {e.get('to_label')}' ECOD slipped from '{edge.expected_date}' to '{new_date}'. SCOD is '{e.get('scd')}'.",
                            block=e.get("from_label"),
                            category="COD"
                        ))
                    else:
                        db.add(Notification(
                            project_name=pm.project,
                            module="Transmission",
                            change_type="Date Delay",
                            message=f"Line '{e.get('from_label')} to {e.get('to_label')}' expected date changed from '{edge.expected_date}' to '{new_date}'",
                            category="Dates"
                        ))
                if edge.contractor and edge.contractor != new_contractor:
                    db.add(Notification(
                        project_name=pm.project,
                        module="Transmission",
                        change_type="Contractor Change",
                        message=f"Line '{e.get('from_label')} to {e.get('to_label')}' contractor changed from '{edge.contractor}' to '{new_contractor}'",
                        category="Scope"
                    ))
                    
                edge.from_node = global_edge.get("from")
                edge.from_label = e.get("from_label")
                edge.to_node = global_edge.get("to")
                edge.to_label = e.get("to_label")
                edge.projects = json.dumps({"projects": global_edge.get("project", []), "phases": global_edge.get("phases", [])})
                edge.contractor = new_contractor
                edge.voltage = e.get("voltage")
                edge.length = str(e.get("length") or global_edge.get("length"))
                edge.status = new_status
                edge.normalized_status = e.get("normalized_status")
                edge.erection = e.get("erection")
                edge.foundation = e.get("foundation")
                edge.stringing = e.get("stringing")
                edge.expected_date = new_date
                edge.scd = e.get("scd")
                edge.charged_date = e.get("charged_date")
                edge.is_delayed = e.get("is_delayed", False)
            else:
                edge = TcNetworkEdge(
                    region=region,
                    edge_id=edge_id,
                    from_node=global_edge.get("from"),
                    from_label=e.get("from_label"),
                    to_node=global_edge.get("to"),
                    to_label=e.get("to_label"),
                    projects=json.dumps({"projects": global_edge.get("project", []), "phases": global_edge.get("phases", [])}),
                    contractor=new_contractor,
                    voltage=e.get("voltage"),
                    length=str(e.get("length") or global_edge.get("length")),
                    status=new_status,
                    normalized_status=e.get("normalized_status"),
                    erection=e.get("erection"),
                    foundation=e.get("foundation"),
                    stringing=e.get("stringing"),
                    expected_date=new_date,
                    scd=e.get("scd"),
                    charged_date=e.get("charged_date"),
                    is_delayed=e.get("is_delayed", False),
                    mapping_id=pm.id
                )
                db.add(edge)
                
                is_currently_delayed = e.get("is_delayed", False)
                is_in_progress = e.get("normalized_status") == 'in_progress'
                if is_currently_delayed and is_in_progress:
                    db.add(Notification(
                        project_name=pm.project,
                        module="Transmission",
                        change_type="COD Delay",
                        message=f"Transmission Delay Warning: Line '{e.get('from_label')} to {e.get('to_label')}' ECOD ({new_date}) is higher than SCOD ({e.get('scd')}).",
                        block=e.get("from_label")
                    ))
                
    # Delete stale edges and entries
    for key, pe in existing_entries.items():
        if key not in seen_entry_keys:
            db.delete(pe)
            
    for key, e in existing_edges.items():
        if key not in seen_edge_keys:
            db.delete(e)
            
    db.commit()
    logger.info(f"Synced {region} Data")
    return True

def run_sync():
    logger.info("Starting Transmission Data Sync...")
    token = get_auth_token()
    if not token:
        logger.error("Sync aborted: No auth token.")
        return False

    db = SessionLocal()
    try:
        khavda_complete = sync_region_data(db, token, "Khavda")
        rajasthan_complete = sync_region_data(db, token, "Rajasthan")
        if not khavda_complete or not rajasthan_complete:
            raise TcSyncError("One or more TC regions did not complete")

        logger.info("Transmission Data Sync Complete!")
        return True
    except Exception as e:
        logger.error(f"Error during sync: {e}")
        db.rollback()
        return False
    finally:
        db.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_sync()
