"""
Akasha Tools Layer — Transmission Connectivity (TC) Tools

MCP-style tool functions for deterministic, read-only access to
transmission network data (substations, lines, progress tracking).
"""

import logging
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)


def _parse_pct(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace('%', '')
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _calc_delay_days(expected_str: str, scd_str: str) -> int | None:
    if not expected_str or not scd_str:
        return None
    try:
        # Parse Mon-YY format (e.g. Mar-27, Oct-26)
        expected = datetime.strptime(expected_str, "%b-%y")
        scheduled = datetime.strptime(scd_str, "%b-%y")
        difference = (expected - scheduled).days
        return difference if difference > 0 else 0
    except (TypeError, ValueError):
        return None


def _average_pct(*values: float | None) -> float | None:
    available = [value for value in values if value is not None]
    return round(sum(available) / len(available), 1) if available else None


def _latest_edges_query(db: Session):
    latest_times = db.query(
        models.TcNetworkEdge.region.label("region"),
        models.TcNetworkEdge.edge_id.label("edge_id"),
        func.max(models.TcNetworkEdge.upload_time).label("max_time"),
    ).group_by(models.TcNetworkEdge.region, models.TcNetworkEdge.edge_id).subquery()
    latest_ids = db.query(
        func.max(models.TcNetworkEdge.id).label("id")
    ).join(
        latest_times,
        (models.TcNetworkEdge.region == latest_times.c.region)
        & (models.TcNetworkEdge.edge_id == latest_times.c.edge_id)
        & (models.TcNetworkEdge.upload_time == latest_times.c.max_time),
    ).group_by(models.TcNetworkEdge.region, models.TcNetworkEdge.edge_id).subquery()
    return db.query(models.TcNetworkEdge).join(
        latest_ids, models.TcNetworkEdge.id == latest_ids.c.id
    )


def _latest_nodes_query(db: Session):
    latest_times = db.query(
        models.TcNetworkNode.region.label("region"),
        models.TcNetworkNode.node_id.label("node_id"),
        func.max(models.TcNetworkNode.upload_time).label("max_time"),
    ).group_by(models.TcNetworkNode.region, models.TcNetworkNode.node_id).subquery()
    latest_ids = db.query(
        func.max(models.TcNetworkNode.id).label("id")
    ).join(
        latest_times,
        (models.TcNetworkNode.region == latest_times.c.region)
        & (models.TcNetworkNode.node_id == latest_times.c.node_id)
        & (models.TcNetworkNode.upload_time == latest_times.c.max_time),
    ).group_by(models.TcNetworkNode.region, models.TcNetworkNode.node_id).subquery()
    return db.query(models.TcNetworkNode).join(
        latest_ids, models.TcNetworkNode.id == latest_ids.c.id
    )


def tc_get_project_lines(db: Session, project_id: str) -> dict:
    """Get transmission line status for a project.
    
    Use when: user asks about transmission progress, grid connectivity, line status.
    """
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()
    
    if not mapping:
        return {"project_id": project_id, "has_data": False}
    
    edges = _latest_edges_query(db).filter(
        models.TcNetworkEdge.mapping_id == mapping.id
    ).order_by(
        models.TcNetworkEdge.region.asc(), models.TcNetworkEdge.edge_id.asc()
    ).all()
    
    if not edges:
        return {"project_id": project_id, "has_data": False, "total_lines": 0}
    
    lines = []
    completed = in_progress = not_started = unknown = delayed = 0
    
    for e in edges:
        f_pct = _parse_pct(e.foundation)
        e_pct = _parse_pct(e.erection)
        s_pct = _parse_pct(e.stringing)
        avg_progress = _average_pct(f_pct, e_pct, s_pct)
        
        status_lower = (e.normalized_status or e.status or "").lower()
        if "completed" in status_lower or "commissioned" in status_lower:
            completed += 1
        elif "progress" in status_lower or (avg_progress is not None and avg_progress > 0):
            in_progress += 1
        elif "not started" in status_lower or (
            all(value is not None for value in (f_pct, e_pct, s_pct)) and avg_progress == 0
        ):
            not_started += 1
        else:
            unknown += 1
        
        if e.is_delayed:
            delayed += 1
        
        days_delayed = _calc_delay_days(e.expected_date, e.scd)
        
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
        })
    
    latest_upload = max((e.upload_time for e in edges if e.upload_time), default=None)
    
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
    query = _latest_edges_query(db).with_entities(
        models.TcNetworkEdge,
        models.ProjectMapping.project_id,
        models.ProjectMapping.project_name_from_p6,
        models.ProjectMapping.project,
    ).outerjoin(
        models.ProjectMapping, models.TcNetworkEdge.mapping_id == models.ProjectMapping.id
    ).filter(
        models.TcNetworkEdge.is_delayed == True
    )
    if region:
        query = query.filter(models.TcNetworkEdge.region == region)
    edges = query.all()
    
    result = []
    # Build mapping lookup for project names
    for e, mapped_project_id, p6_name, mapped_name in edges:
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
            "_source_table": "tc_network_edge",
        })
    result.sort(key=lambda x: (-x["days_delayed"], str(x["edge_id"]), str(x["region"])))
    return result[:limit]


def tc_get_network_summary(db: Session) -> dict:
    """Get overall transmission network summary — nodes and edges.
    
    Use when: user asks about transmission network overview.
    """
    total_nodes = _latest_nodes_query(db).count()
    edge_query = _latest_edges_query(db)
    total_edges = edge_query.count()
    delayed_edges = edge_query.filter(
        models.TcNetworkEdge.is_delayed == True
    ).count()
    
    return {
        "total_substations": total_nodes,
        "total_lines": total_edges,
        "delayed_lines": delayed_edges,
        "_source_table": "tc_network_node, tc_network_edge",
    }


def tc_get_freshness(db: Session) -> dict:
    """Get the latest upload timestamp for TC data."""
    latest = db.query(func.max(models.TcNetworkEdge.upload_time)).scalar()
    return {
        "synced_at": latest.isoformat() if latest else None,
        "exists": latest is not None,
    }
