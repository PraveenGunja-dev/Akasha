"""
Akasha Tools Layer — Cross-Domain Portfolio Tools

Higher-level tools that combine data from multiple domains (P6 + SAP + TC)
and provide portfolio-wide analytics.
"""

import logging
from sqlalchemy.orm import Session

import models
from engine.project_resolver import resolve_project
from engine.tools.p6_tools import p6_get_project_summary, p6_list_all_projects
from engine.tools.sap_tools import sap_get_po_summary
from engine.tools.tc_tools import tc_get_project_lines

logger = logging.getLogger(__name__)


def portfolio_get_project_list(db: Session) -> list[dict]:
    """Get list of all mapped projects with their identifiers.
    
    Use when: need to resolve a project name to an ID, or list available projects.
    """
    mappings = db.query(models.ProjectMapping).all()
    filtered_mappings = []
    for m in mappings:
        name_check = m.project_name_from_p6 or m.project or ""
        if "demo" not in name_check.lower():
            filtered_mappings.append(m)
            
    return [{
        "project_id": m.project_id,
        "project_name": m.project,
        "p6_name": m.project_name_from_p6,
        "spv_name": m.spv_name,
        "category": m.category,
        "capacity_mwac": m.capacity_mwac,
        "cluster": m.cluster,
        "subcluster": m.subcluster,
    } for m in filtered_mappings]


def portfolio_get_project_360(db: Session, project_id: str) -> dict:
    """Get a full 360-degree view of a project (P6 + SAP + TC combined).
    
    Use when: user asks for comprehensive project analysis, needs cross-domain context.
    This is the "expensive" call — only use when needed, prefer domain-specific tools otherwise.
    """
    p6_data = p6_get_project_summary(db, project_id)
    sap_data = sap_get_po_summary(db, project_id)
    tc_data = tc_get_project_lines(db, project_id)
    
    # Get project-specific notifications. Notifications are keyed by display name
    # in the current schema, while chatbot tools work with canonical project IDs.
    display_name = get_project_display_name(db, project_id)
    all_notifs = db.query(models.Notification).filter(
        models.Notification.project_name.in_([project_id, display_name])
    ).order_by(models.Notification.created_at.desc()).limit(10).all()
    notifications = [{
        "id": n.id,
        "title": n.activity_name or n.change_type or "Notification",
        "message": n.message,
        "status": n.action_status,
        "category": n.category,
        "project_name": n.project_name,
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


def portfolio_get_riskiest_projects(db: Session, top_n: int = 5) -> dict:
    """Get the top-N riskiest projects across the portfolio.
    
    Use when: user asks about which projects are most at risk, portfolio risk overview.
    """
    all_projects_data = p6_list_all_projects(db)
    projects = all_projects_data.get("projects", [])
    
    # Score by SPI deviation + negative float
    scored = []
    for p in projects:
        spi = p.get("spi") or 1.0
        float_val = p.get("total_float") or 0
        # Lower SPI and more negative float = higher risk score
        risk_score = max(0, 1 - spi) * 100 + max(0, -float_val) * 0.1
        scored.append({**p, "risk_score": round(risk_score, 2)})
    
    scored.sort(key=lambda x: x["risk_score"], reverse=True)
    return {
        "total_portfolio_projects": len(projects),
        "showing_top_n": top_n,
        "riskiest_projects": scored[:top_n]
    }


def get_project_display_name(db: Session, project_id: str) -> str:
    """Get the human-readable display name for a project_id.
    
    Returns the best available name: project_name_from_p6 > project > project_id.
    All tools should use this to include project_name in their responses.
    """
    if not project_id:
        return "Unknown"
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()
    if mapping:
        return mapping.project_name_from_p6 or mapping.project or project_id
    # Fallback: check P6 project table
    p6 = db.query(models.P6Project).filter(
        models.P6Project.project_id == project_id
    ).first()
    if p6 and p6.name:
        return p6.name
    return project_id


def portfolio_resolve_project_id(db: Session, name_or_id: str) -> dict | None:
    """Resolve a fuzzy project name, SPV name, or P6 name to the canonical project_id AND project_name.
    
    Use when: user mentions a project by name and we need the canonical ID.
    Returns: dict with project_id, project_name, p6_name — or None if not found.
    Tries: project_id → project → project_name_from_p6 → P6 name → fuzzy match.
    """
    if not name_or_id:
        return None
    
    def _build_result(mapping):
        return {
            "project_id": mapping.project_id,
            "project_name": mapping.project_name_from_p6 or mapping.project or mapping.project_id,
            "p6_name": mapping.project_name_from_p6 or "",
            "spv_name": mapping.spv_name or "",
            "category": mapping.category or "",
            "capacity_mwac": mapping.capacity_mwac,
        }

    def _build_p6_result(p6):
        mapping = db.query(models.ProjectMapping).filter(
            models.ProjectMapping.project_id == p6.project_id
        ).first()
        if mapping:
            return _build_result(mapping)
        return {
            "project_id": p6.project_id,
            "project_name": p6.name or p6.project_id,
            "p6_name": p6.name or "",
            "spv_name": "",
            "category": "",
            "capacity_mwac": None,
        }

    for resolution in (
        resolve_project(db, name_or_id),
        resolve_project(db, None, message=name_or_id),
    ):
        if resolution.status == "resolved" and resolution.project_ids:
            p6 = db.query(models.P6Project).filter(
                models.P6Project.project_id == resolution.project_ids[0]
            ).first()
            if p6 and p6.project_id:
                return _build_p6_result(p6)
            m = db.query(models.ProjectMapping).filter(
                models.ProjectMapping.project_id == resolution.project_ids[0]
            ).first()
            if m and m.project_id:
                return _build_result(m)

    # Preserve the older P6-name fallback for mapped projects whose name only
    # exists in the P6 table.
    name_or_id = name_or_id.strip()
    p6 = db.query(models.P6Project).filter(
        models.P6Project.name == name_or_id
    ).first()
    if p6:
        return _build_p6_result(p6)
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
            "title": n.activity_name or n.change_type or "Notification",
            "message": n.message,
            "category": n.category,
            "status": n.action_status,
            "project_name": n.project_name,
            "ai_suggestion": n.ai_suggestion
        })
    return result
