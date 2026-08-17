from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import TcProjectEntry, TcNetworkEdge, TcNetworkNode, TcLineGeometry
import json

router = APIRouter(
    prefix="/api/tc",
    tags=["transmission"]
)

@router.get("/khavda/projects")
def get_khavda_projects(db: Session = Depends(get_db)):
    entries = db.query(TcProjectEntry).filter(TcProjectEntry.region == "Khavda").all()
    return {"projects": entries}

def _build_network(db: Session, region: str):
    nodes = db.query(TcNetworkNode).filter(TcNetworkNode.region == region).all()
    edges = db.query(TcNetworkEdge).filter(TcNetworkEdge.region == region).all()

    # Traced route geometry, where scripts/ingest_line_geometry.py has matched one.
    # Edges without a match fall back to a straight substation-to-substation chord.
    geometry_by_edge = {}
    for g in db.query(TcLineGeometry).filter(TcLineGeometry.region == region).all():
        try:
            geometry_by_edge[g.edge_id] = {
                "path": json.loads(g.path) if g.path else None,
                "path_source": g.source,
                "path_confidence": g.match_confidence,
                "path_length_km": g.length_km,
            }
        except Exception:
            continue

    # Deduplicate edges by edge_id since they are duplicated per mapping_id in DB
    seen_edges = set()
    unique_edges = []
    for e in edges:
        if e.edge_id not in seen_edges:
            seen_edges.add(e.edge_id)
            unique_edges.append(e)

    # Parse the projects JSON back into lists for the frontend
    processed_edges = []
    for e in unique_edges:
        edge_dict = {
            "id": e.edge_id,
            "region": e.region,
            "from": e.from_node,
            "from_label": e.from_label,
            "to": e.to_node,
            "to_label": e.to_label,
            "contractor": e.contractor,
            "voltage": e.voltage,
            "length": e.length,
            "status": e.status,
            "normalized_status": e.normalized_status,
            "erection": e.erection,
            "foundation": e.foundation,
            "stringing": e.stringing,
            "expected_date": e.expected_date,
            "mapping_id": e.mapping_id,
            "projects": [],
            "path": None,
            "path_source": None,
            "path_confidence": None,
            "path_length_km": None,
        }
        edge_dict.update(geometry_by_edge.get(e.edge_id, {}))

        if e.projects:
            try:
                parsed = json.loads(e.projects)
                if isinstance(parsed, dict):
                    edge_dict["projects"] = parsed.get("projects", [])
                elif isinstance(parsed, list):
                    edge_dict["projects"] = parsed
            except Exception:
                pass

        processed_edges.append(edge_dict)

    processed_nodes = [
        {
            "id": n.node_id,
            "region": n.region,
            "label": n.label,
            "type": n.type,
            "status": n.status,
            "x": n.x,
            "y": n.y
        } for n in nodes
    ]

    return {
        "nodes": processed_nodes,
        "edges": processed_edges
    }

@router.get("/rajasthan/network")
def get_rajasthan_network(db: Session = Depends(get_db)):
    return _build_network(db, "Rajasthan")

@router.get("/khavda/network")
def get_khavda_network(db: Session = Depends(get_db)):
    return _build_network(db, "Khavda")
