"""
Akasha Tools Layer — Transmission Connectivity (TC) Tools

MCP-style tool functions for deterministic, read-only access to
transmission network data (substations, lines, progress tracking).
"""

import logging
import json
from datetime import date, datetime
from sqlalchemy.orm import Session

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


def tc_get_project_lines(db: Session, project_id: str) -> dict:
    """Get transmission line status for a project.
    
    Use when: user asks about transmission progress, grid connectivity, line status.
    """
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()
    
    if not mapping:
        return {"project_id": project_id, "has_data": False}
    
    edges = db.query(models.TcNetworkEdge).filter(
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
        
        lines.append({
            "edge_id": e.edge_id,
            "from_label": e.from_label,
            "to_label": e.to_label,
            "status": e.status,
            "contractor": e.contractor,
            "voltage": e.voltage,
            "foundation_pct": f_pct,
            "erection_pct": e_pct,
            "stringing_pct": s_pct,
            "avg_progress": round(avg_progress, 1),
            "is_delayed": e.is_delayed,
            "expected_date": e.expected_date,
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
    edges = db.query(models.TcNetworkEdge).filter(
        models.TcNetworkEdge.is_delayed == True
    ).all()
    
    result = []
    for e in edges:
        f_pct = _parse_pct(e.foundation)
        e_pct = _parse_pct(e.erection)
        s_pct = _parse_pct(e.stringing)
        
        result.append({
            "edge_id": e.edge_id,
            "from_label": e.from_label,
            "to_label": e.to_label,
            "status": e.status,
            "contractor": e.contractor,
            "foundation_pct": f_pct,
            "erection_pct": e_pct,
            "stringing_pct": s_pct,
            "expected_date": e.expected_date,
            "_source_table": "tc_network_edge",
        })
    
    return result


def tc_get_network_summary(db: Session) -> dict:
    """Get overall transmission network summary — nodes and edges.
    
    Use when: user asks about transmission network overview.
    """
    total_nodes = db.query(models.TcNetworkNode).count()
    total_edges = db.query(models.TcNetworkEdge).count()
    delayed_edges = db.query(models.TcNetworkEdge).filter(
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
