from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from services import transmission_service as transmission

router = APIRouter(
    prefix="/api/tc",
    tags=["transmission"]
)

@router.get("/khavda/projects")
def get_khavda_projects(db: Session = Depends(get_db)):
    entries = transmission.latest_project_entries(db, "Khavda")
    return {"projects": entries}

@router.get("/rajasthan/network")
def get_rajasthan_network(db: Session = Depends(get_db)):
    network = transmission.region_network(db, "Rajasthan")
    processed_edges = []
    for edge in network["edges"]:
        edge_dict = {
            "id": edge["edge_id"],
            "from": edge["from_node"],
            "from_label": edge["from_label"],
            "to": edge["to_node"],
            "to_label": edge["to_label"],
            "contractor": edge["contractor"],
            "voltage": edge["voltage"],
            "length": edge["length"],
            "status": edge["status"],
            "normalized_status": edge["normalized_status"],
            "erection": edge["erection"],
            "foundation": edge["foundation"],
            "stringing": edge["stringing"],
            "expected_date": edge["expected_date"],
            "mapping_id": edge["mapping_id"],
            "projects": edge["projects"],
            "phases": edge["phases"],
            "canonical_status": edge["canonical_status"],
            "avg_progress": edge["avg_progress"],
            "is_delayed": edge["is_delayed"],
            "days_delayed": edge["days_delayed"],
            "expected_date_iso": edge["expected_date_iso"],
        }
        processed_edges.append(edge_dict)

    return {
        "nodes": network["nodes"],
        "edges": processed_edges,
        "freshness": network["freshness"],
    }
