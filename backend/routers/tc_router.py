from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from models import TcProjectEntry, TcNetworkEdge, TcNetworkNode
import json

router = APIRouter(
    prefix="/api/tc",
    tags=["transmission"]
)

@router.get("/khavda/projects")
def get_khavda_projects(db: Session = Depends(get_db)):
    entries = db.query(TcProjectEntry).filter(TcProjectEntry.region == "Khavda").all()
    return {"projects": entries}

@router.get("/rajasthan/network")
def get_rajasthan_network(db: Session = Depends(get_db)):
    nodes = db.query(TcNetworkNode).filter(TcNetworkNode.region == "Rajasthan").all()
    edges = db.query(TcNetworkEdge).filter(TcNetworkEdge.region == "Rajasthan").all()
    
    # Parse the projects JSON back into lists for the frontend
    processed_edges = []
    for e in edges:
        edge_dict = {
            "id": e.edge_id,
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
            "projects": json.loads(e.projects) if e.projects else []
        }
        processed_edges.append(edge_dict)
        
    processed_nodes = [
        {
            "id": n.node_id,
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
