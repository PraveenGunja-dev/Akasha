"""
Akasha Tools Layer — Transmission Connectivity (TC) Tools

MCP-style tool functions for deterministic, read-only access to
transmission network data (substations, lines, progress tracking).
"""

import logging
import json
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import func

import models

logger = logging.getLogger(__name__)


def _parse_pct(value) -> float:
    if value is None:
        return 0.0
    s = str(value).strip().replace('%', '')
    try:
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def _calc_delay_days(expected_str: str, scd_str: str) -> int:
    if not expected_str or not scd_str:
        return 0
    try:
        from datetime import datetime
        # Parse Mon-YY format (e.g. Mar-27, Oct-26)
        exp = datetime.strptime(expected_str, "%b-%y")
        scd = datetime.strptime(scd_str, "%b-%y")
        diff = (exp - scd).days
        return diff if diff > 0 else 0
    except Exception:
        return 0


def tc_get_project_lines(db: Session, project_id: str) -> dict:
    """Get transmission line status for a project.
    
    Use when: user asks about transmission progress, grid connectivity, line status.
    """
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()
    
    if not mapping:
        return {"project_id": project_id, "has_data": False}
    
    subq = db.query(
        models.TcNetworkEdge.edge_id, 
        func.max(models.TcNetworkEdge.upload_time).label('max_time')
    ).group_by(models.TcNetworkEdge.edge_id).subquery()
    
    edges = db.query(models.TcNetworkEdge).join(
        subq, 
        (models.TcNetworkEdge.edge_id == subq.c.edge_id) & 
        (models.TcNetworkEdge.upload_time == subq.c.max_time)
    ).filter(
        models.TcNetworkEdge.mapping_id == mapping.id
    ).all()
    
    if not edges:
        return {"project_id": project_id, "has_data": False, "total_lines": 0}
    
    today = date.today()
    lines = []
    completed = in_progress = not_started = delayed = 0
    
    for e in edges:
        f_pct = _parse_pct(e.foundation)
        e_pct = _parse_pct(e.erection)
        s_pct = _parse_pct(e.stringing)
        avg_progress = (f_pct + e_pct + s_pct) / 3
        
        status_lower = (e.normalized_status or e.status or "").lower()
        if "completed" in status_lower or "commissioned" in status_lower:
            completed += 1
        elif avg_progress > 0:
            in_progress += 1
        else:
            not_started += 1
        
        if e.is_delayed:
            delayed += 1
        
        days_delayed = _calc_delay_days(e.expected_date, e.scd)
        
        lines.append({
            "edge_id": e.edge_id,
            "from_label": e.from_label,
            "to_label": e.to_label,
            "status": e.status,
            "contractor": e.contractor,
            "projects": e.projects,
            "voltage": e.voltage,
            "foundation_pct": f_pct,
            "erection_pct": e_pct,
            "stringing_pct": s_pct,
            "avg_progress": round(avg_progress, 1),
            "is_delayed": e.is_delayed,
            "expected_date": e.expected_date,
            "scd": e.scd,
            "days_delayed": days_delayed,
        })
    
    latest_upload = max((e.upload_time for e in edges if e.upload_time), default=None)
    
    return {
        "project_id": project_id,
        "has_data": True,
        "total_lines": len(edges),
        "completed": completed,
        "in_progress": in_progress,
        "not_started": not_started,
        "delayed": delayed,
        "lines": lines,
        "_source_table": "tc_network_edge",
        "_synced_at": latest_upload.isoformat() if latest_upload else None,
    }


def tc_get_at_risk_lines(db: Session, days_threshold: int = 60) -> list[dict]:
    """Get all transmission lines at risk across the portfolio.
    
    Use when: user asks about transmission risks, delayed lines, grid bottlenecks.
    """
    today = date.today()
    subq = db.query(
        models.TcNetworkEdge.edge_id, 
        func.max(models.TcNetworkEdge.upload_time).label('max_time')
    ).group_by(models.TcNetworkEdge.edge_id).subquery()
    
    edges = db.query(models.TcNetworkEdge).join(
        subq, 
        (models.TcNetworkEdge.edge_id == subq.c.edge_id) & 
        (models.TcNetworkEdge.upload_time == subq.c.max_time)
    ).filter(
        models.TcNetworkEdge.is_delayed == True
    ).all()
    
    result = []
    for e in edges:
        f_pct = _parse_pct(e.foundation)
        e_pct = _parse_pct(e.erection)
        s_pct = _parse_pct(e.stringing)
        days_delayed = _calc_delay_days(e.expected_date, e.scd)
        
        result.append({
            "edge_id": e.edge_id,
            "region": e.region,
            "from_label": e.from_label,
            "to_label": e.to_label,
            "status": e.status,
            "contractor": e.contractor,
            "projects": e.projects,
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
    
    return result


def tc_get_network_summary(db: Session) -> dict:
    """Get overall transmission network summary — nodes and edges.
    
    Use when: user asks about transmission network overview.
    """
    node_subq = db.query(
        models.TcNetworkNode.node_id, 
        func.max(models.TcNetworkNode.upload_time).label('max_time')
    ).group_by(models.TcNetworkNode.node_id).subquery()
    total_nodes = db.query(models.TcNetworkNode).join(
        node_subq, 
        (models.TcNetworkNode.node_id == node_subq.c.node_id) & 
        (models.TcNetworkNode.upload_time == node_subq.c.max_time)
    ).count()

    edge_subq = db.query(
        models.TcNetworkEdge.edge_id, 
        func.max(models.TcNetworkEdge.upload_time).label('max_time')
    ).group_by(models.TcNetworkEdge.edge_id).subquery()
    
    total_edges = db.query(models.TcNetworkEdge).join(
        edge_subq, 
        (models.TcNetworkEdge.edge_id == edge_subq.c.edge_id) & 
        (models.TcNetworkEdge.upload_time == edge_subq.c.max_time)
    ).count()
    
    delayed_edges = db.query(models.TcNetworkEdge).join(
        edge_subq, 
        (models.TcNetworkEdge.edge_id == edge_subq.c.edge_id) & 
        (models.TcNetworkEdge.upload_time == edge_subq.c.max_time)
    ).filter(
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
    from sqlalchemy import func
    latest = db.query(func.max(models.TcNetworkEdge.upload_time)).scalar()
    return {
        "synced_at": latest.isoformat() if latest else None,
        "exists": latest is not None,
    }
