"""
Akasha Tools Layer — Transmission Connectivity (TC) Tools

MCP-style tool functions for deterministic, read-only access to
transmission network data (substations, lines, progress tracking).
"""

import logging
from sqlalchemy.orm import Session

import models
from services import transmission_service as transmission

logger = logging.getLogger(__name__)


def _parse_pct(value) -> float | None:
    return transmission.parse_progress(value)


def _calc_delay_days(expected_str: str, scd_str: str) -> int | None:
    class Dates:
        expected_date = expected_str
        scd = scd_str

    return transmission.delay_days(Dates())


def tc_get_project_lines(db: Session, project_id: str) -> dict:
    """Get transmission line status for a project.
    
    Use when: user asks about transmission progress, grid connectivity, line status.
    """
    mapping, _, edges = transmission.project_edges(db, project_id)
    
    if not mapping:
        return {
            "project_id": project_id,
            "has_data": False,
            **transmission.readiness_from_counts(
                total_lines=0, completed=0, in_progress=0,
                not_started=0, unknown=0, delayed=0,
            ),
        }
    
    if not edges:
        return {
            "project_id": project_id,
            "has_data": False,
            "total_lines": 0,
            **transmission.readiness_from_counts(
                total_lines=0, completed=0, in_progress=0,
                not_started=0, unknown=0, delayed=0,
            ),
        }
    
    lines = []
    completed = in_progress = not_started = unknown = delayed = 0
    
    for e in edges:
        dto = transmission.edge_dict(e)
        f_pct = dto["foundation_pct"]
        e_pct = dto["erection_pct"]
        s_pct = dto["stringing_pct"]
        avg_progress = dto["avg_progress"]

        if dto["canonical_status"] == "completed":
            completed += 1
        elif dto["canonical_status"] == "in_progress":
            in_progress += 1
        elif dto["canonical_status"] == "not_started":
            not_started += 1
        else:
            unknown += 1
        
        if e.is_delayed:
            delayed += 1
        
        days_delayed = dto["days_delayed"]
        
        lines.append({
            "edge_id": e.edge_id,
            "region": e.region,
            "from_label": e.from_label,
            "to_label": e.to_label,
            "status": e.status,
            "contractor": e.contractor,
            "projects": e.projects,
            "voltage": e.voltage,
            "foundation_pct": f_pct,
            "erection_pct": e_pct,
            "stringing_pct": s_pct,
            "avg_progress": avg_progress,
            "is_delayed": e.is_delayed,
            "expected_date": e.expected_date,
            "scd": e.scd,
            "days_delayed": days_delayed,
            "canonical_status": dto["canonical_status"],
            "expected_date_iso": dto["expected_date_iso"],
            "scd_iso": dto["scd_iso"],
        })
    
    latest_upload = max((e.upload_time for e in edges if e.upload_time), default=None)
    readiness = transmission.readiness_from_counts(
        total_lines=len(edges),
        completed=completed,
        in_progress=in_progress,
        not_started=not_started,
        unknown=unknown,
        delayed=delayed,
    )
    
    from engine.tools.portfolio_tools import get_project_display_name
    project_name = get_project_display_name(db, project_id)
    
    return {
        "project_id": project_id,
        "project_name": project_name,
        "has_data": True,
        "total_lines": len(edges),
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
        "unknown": unknown,
        "delayed": delayed,
        **readiness,
        "lines": lines,
        "_source_table": "tc_network_edge",
        "_synced_at": latest_upload.isoformat() if latest_upload else None,
    }


def tc_search_lines(
    db: Session,
    region: str,
    delayed_only: bool = False,
    limit: int = 100,
) -> dict:
    """Search the latest transmission-line records for one state or region."""
    normalized_region = transmission.normalize_region(region)
    edges = transmission.latest_physical_edges(db, region)
    if delayed_only:
        edges = [edge for edge in edges if edge.is_delayed]

    total_matching = len(edges)
    latest_upload = max((edge.upload_time for edge in edges if edge.upload_time), default=None)
    edges = edges[:limit]
    completed = in_progress = not_started = unknown = delayed = 0
    lines = []
    for edge in edges:
        dto = transmission.edge_dict(edge)
        foundation_pct = dto["foundation_pct"]
        erection_pct = dto["erection_pct"]
        stringing_pct = dto["stringing_pct"]
        average_progress = dto["avg_progress"]
        if dto["canonical_status"] == "completed":
            completed += 1
        elif dto["canonical_status"] == "in_progress":
            in_progress += 1
        elif dto["canonical_status"] == "not_started":
            not_started += 1
        else:
            unknown += 1
        if edge.is_delayed:
            delayed += 1

        lines.append({
            "edge_id": edge.edge_id,
            "region": edge.region,
            "from_label": edge.from_label,
            "to_label": edge.to_label,
            "status": edge.status,
            "contractor": edge.contractor,
            "projects": edge.projects,
            "voltage": edge.voltage,
            "length": edge.length,
            "foundation_pct": foundation_pct,
            "erection_pct": erection_pct,
            "stringing_pct": stringing_pct,
            "avg_progress": average_progress,
            "is_delayed": edge.is_delayed,
            "expected_date": edge.expected_date,
            "scd": edge.scd,
            "charged_date": edge.charged_date,
            "days_delayed": _calc_delay_days(edge.expected_date, edge.scd),
            "canonical_status": dto["canonical_status"],
            "expected_date_iso": dto["expected_date_iso"],
            "scd_iso": dto["scd_iso"],
        })

    return {
        "region": transmission.normalize_region(edges[0].region) if edges else normalized_region,
        "has_data": total_matching > 0,
        "total_matching": total_matching,
        "returned": len(lines),
        "delayed_only": delayed_only,
        "status_breakdown_for_returned_lines": {
            "completed": completed,
            "in_progress": in_progress,
            "not_started": not_started,
            "unknown": unknown,
            "delayed": delayed,
        },
        "lines": lines,
        "_source_table": "tc_network_edge",
        "_synced_at": latest_upload.isoformat() if latest_upload else None,
    }


def tc_get_at_risk_lines(
    db: Session,
    days_threshold: int = 60,
    limit: int = 15,
    region: str | None = None,
) -> list[dict]:
    """Get all transmission lines at risk across the portfolio.
    
    Use when: user asks about transmission risks, delayed lines, grid bottlenecks.
    """
    edges = [edge for edge in transmission.latest_physical_edges(db, region) if edge.is_delayed]
    mappings = {
        mapping.id: mapping
        for mapping in db.query(models.ProjectMapping).all()
    }
    
    result = []
    # Build mapping lookup for project names
    for e in edges:
        dto = transmission.edge_dict(e)
        mapping = mappings.get(e.mapping_id)
        mapped_project_id = mapping.project_id if mapping else None
        p6_name = mapping.project_name_from_p6 if mapping else None
        mapped_name = mapping.project if mapping else None
        f_pct = _parse_pct(e.foundation)
        e_pct = _parse_pct(e.erection)
        s_pct = _parse_pct(e.stringing)
        days_delayed = _calc_delay_days(e.expected_date, e.scd)
        if days_delayed is None or days_delayed < days_threshold:
            continue
        
        # Resolve project name
        proj_name = p6_name or mapped_name or mapped_project_id or "Unknown"
        
        result.append({
            "edge_id": e.edge_id,
            "region": e.region,
            "from_label": e.from_label,
            "to_label": e.to_label,
            "status": e.status,
            "contractor": e.contractor,
            "projects": e.projects,
            "mapped_project_id": mapped_project_id,
            "project_name": proj_name,
            "voltage": e.voltage,
            "length": e.length,
            "foundation_pct": f_pct,
            "erection_pct": e_pct,
            "stringing_pct": s_pct,
            "expected_date": e.expected_date,
            "scd": e.scd,
            "charged_date": e.charged_date,
            "days_delayed": days_delayed,
            "canonical_status": dto["canonical_status"],
            "avg_progress": dto["avg_progress"],
            "expected_date_iso": dto["expected_date_iso"],
            "scd_iso": dto["scd_iso"],
            "_source_table": "tc_network_edge",
        })
    result.sort(key=lambda x: (-x["days_delayed"], str(x["edge_id"]), str(x["region"])))
    return result[:limit]


def tc_get_network_summary(db: Session) -> dict:
    """Get overall transmission network summary — nodes and edges.
    
    Use when: user asks about transmission network overview.
    """
    total_nodes = len(transmission.latest_nodes(db))
    edges = transmission.latest_physical_edges(db)
    total_edges = len(edges)
    delayed_edges = sum(1 for edge in edges if edge.is_delayed)
    
    return {
        "total_substations": total_nodes,
        "total_lines": total_edges,
        "delayed_lines": delayed_edges,
        "_source_table": "tc_network_node, tc_network_edge",
    }


def tc_get_freshness(db: Session) -> dict:
    """Get the latest upload timestamp for TC data."""
    result = transmission.freshness(db)
    result.pop("region", None)
    return result
