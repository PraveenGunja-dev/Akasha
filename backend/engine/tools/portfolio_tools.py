"""
Akasha Tools Layer — Cross-Domain Portfolio Tools

Higher-level tools that combine data from multiple domains (P6 + SAP + TC)
and provide portfolio-wide analytics.
"""

import logging
from sqlalchemy.orm import Session

import models
from engine.tools.p6_tools import p6_get_project_summary, p6_list_all_projects
from engine.tools.sap_tools import sap_get_po_summary
from engine.tools.tc_tools import tc_get_project_lines

logger = logging.getLogger(__name__)


def portfolio_get_project_list(db: Session) -> list[dict]:
    """Get list of all mapped projects with their identifiers.
    
    Use when: need to resolve a project name to an ID, or list available projects.
    """
    mappings = db.query(models.ProjectMapping).all()
    return [{
        "project_id": m.project_id,
        "project_name": m.project,
        "p6_name": m.project_name_from_p6,
        "spv_name": m.spv_name,
        "category": m.category,
        "capacity_mwac": m.capacity_mwac,
        "cluster": m.cluster,
        "subcluster": m.subcluster,
    } for m in mappings]


def portfolio_get_project_360(db: Session, project_id: str) -> dict:
    """Get a full 360-degree view of a project (P6 + SAP + TC combined).
    
    Use when: user asks for comprehensive project analysis, needs cross-domain context.
    This is the "expensive" call — only use when needed, prefer domain-specific tools otherwise.
    """
    p6_data = p6_get_project_summary(db, project_id)
    sap_data = sap_get_po_summary(db, project_id)
    tc_data = tc_get_project_lines(db, project_id)
    
    # Get project-specific notifications
    all_notifs = db.query(models.Notification).filter(models.Notification.project_id == project_id).order_by(models.Notification.created_at.desc()).limit(10).all()
    notifications = [{
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "status": n.action_status,
        "category": n.category,
        "ai_suggestion": n.ai_suggestion
    } for n in all_notifs]
    
    # Compute health status
    health = "Healthy"
    risk_factors = []
    
    if p6_data:
        spi = p6_data.get("spi")
        if spi is not None and spi < 0.9:
            health = "Critical" if spi < 0.8 else "At Risk"
            risk_factors.append(f"SPI={spi:.2f} (below threshold)")
        
        float_val = p6_data.get("total_float")
        if float_val is not None and float_val < 0:
            risk_factors.append(f"Negative float: {float_val}h")
    
    if sap_data.get("has_data"):
        fulfillment = sap_data["summary"].get("fulfillment_pct", 100)
        if fulfillment < 80:
            risk_factors.append(f"Material fulfillment at {fulfillment}%")
            if health == "Healthy":
                health = "At Risk"
    
    if tc_data.get("has_data") and tc_data.get("delayed", 0) > 0:
        risk_factors.append(f"{tc_data['delayed']} transmission lines delayed")
    
    # Determine freshest sync time
    sync_times = []
    if p6_data and p6_data.get("last_synced_at"):
        sync_times.append(p6_data["last_synced_at"])
    if sap_data.get("_synced_at"):
        sync_times.append(sap_data["_synced_at"])
    if tc_data.get("_synced_at"):
        sync_times.append(tc_data["_synced_at"])
    
    return {
        "project_id": project_id,
        "health": health,
        "risk_factors": risk_factors,
        "p6": p6_data,
        "sap": sap_data,
        "tc": tc_data,
        "notifications": notifications,
        "data_as_of": min(sync_times) if sync_times else None,
        "_sources_used": ["p6_project", "p6_activity", "mt_poamount", "tc_network_edge", "notifications"],
    }


def portfolio_get_riskiest_projects(db: Session, top_n: int = 5) -> list[dict]:
    """Get the top-N riskiest projects across the portfolio.
    
    Use when: user asks about which projects are most at risk, portfolio risk overview.
    """
    projects = p6_list_all_projects(db)
    
    # Score by SPI deviation + negative float
    scored = []
    for p in projects:
        spi = p.get("spi") or 1.0
        float_val = p.get("total_float") or 0
        # Lower SPI and more negative float = higher risk score
        risk_score = max(0, 1 - spi) * 100 + max(0, -float_val) * 0.1
        scored.append({**p, "risk_score": round(risk_score, 2)})
    
    scored.sort(key=lambda x: x["risk_score"], reverse=True)
    return scored[:top_n]


def portfolio_resolve_project_id(db: Session, name_or_id: str) -> str | None:
    """Resolve a project name, P6 name, or SPV name to a project_id.
    
    Use when: user mentions a project by name and we need the canonical ID.
    Tries: project_id → project → project_name_from_p6 → P6 name → fuzzy match.
    """
    if not name_or_id:
        return None
    
    name_or_id = name_or_id.strip()
    
    # Direct project_id match
    m = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == name_or_id
    ).first()
    if m:
        return m.project_id
    
    # Match against project_mapping.project
    m = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project == name_or_id
    ).first()
    if m and m.project_id:
        return m.project_id
    
    # Match against P6 project name
    p6 = db.query(models.P6Project).filter(
        models.P6Project.name == name_or_id
    ).first()
    if p6:
        m = db.query(models.ProjectMapping).filter(
            models.ProjectMapping.project_id == p6.project_id
        ).first()
        if m:
            return m.project_id
    
    # Match project_name_from_p6
    m = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_name_from_p6 == name_or_id
    ).first()
    if m and m.project_id:
        return m.project_id
    
    # Case-insensitive fuzzy search (contains)
    name_lower = name_or_id.lower()
    all_mappings = db.query(models.ProjectMapping).all()
    for mapping in all_mappings:
        candidates = [
            mapping.project or "",
            mapping.project_name_from_p6 or "",
            mapping.spv_name or "",
        ]
        for candidate in candidates:
            if name_lower in candidate.lower() or candidate.lower() in name_lower:
                return mapping.project_id
    return None

def portfolio_get_notifications(db: Session, limit: int = 10, category: str = "All") -> list[dict]:
    """Get the latest actionable notifications for the user.
    
    Use when: user asks about their notifications, alerts, or what they need to look at.
    """
    query = db.query(models.Notification)
    if category != "All":
        query = query.filter(models.Notification.category == category)
        
    notifs = query.order_by(models.Notification.created_at.desc()).limit(limit).all()
    
    result = []
    for n in notifs:
        result.append({
            "id": n.id,
            "title": n.title,
            "message": n.message,
            "category": n.category,
            "status": n.action_status,
            "project_id": n.project_id,
            "ai_suggestion": n.ai_suggestion
        })
    return result
