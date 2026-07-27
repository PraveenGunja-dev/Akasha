
"""
Akasha Tools Layer — Cross-Domain Portfolio Tools

Higher-level tools that combine data from multiple domains (P6 + SAP + TC)
and provide portfolio-wide analytics.
"""

import difflib
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
    
    # Get project-specific notifications. Notification.project_name is a free-text display
    # string, not the canonical project_id, and P6-side vs TC-side notifications populate it
    # from different fields (P6Project.name vs ProjectMapping.project) — so match against
    # every display name this project is known by, not a single exact string.
    display_names = {project_id}
    if p6_data and p6_data.get("name"):
        display_names.add(p6_data["name"])
    mapping = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == project_id
    ).first()
    if mapping:
        if mapping.project:
            display_names.add(mapping.project)
        if mapping.project_name_from_p6:
            display_names.add(mapping.project_name_from_p6)

    all_notifs = db.query(models.Notification).filter(
        models.Notification.project_name.in_(display_names)
    ).order_by(models.Notification.created_at.desc()).limit(10).all()
    notifications = [{
        "id": n.id,
        "title": n.change_type,
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


def portfolio_get_riskiest_projects(db: Session, top_n: int = 5) -> dict:
    """Get the top-N riskiest projects across the portfolio.

    Use when: user asks about which projects are most at risk, portfolio risk overview.

    Risk is computed by the KPI engine from the underlying P6 activities + SAP POs + TC lines
    (schedule risk = activities behind / total, procurement risk = pending POs / total, execution
    risk = delayed lines / total). It does NOT use the stored SPI/float columns, which are null
    in this database and previously made every project score 0.
    """
    from engine.kpi_engine import compute_portfolio_kpis

    kpis = compute_portfolio_kpis(db)  # already sorted riskiest-first
    riskiest = []
    for r in kpis[:top_n]:
        s = r.get("schedule", {})
        ov = r.get("overall_risk", {})
        riskiest.append({
            "project_id": r["project_id"],
            "project_name": r["project_name"],
            "risk_score": ov.get("overall_risk_pct"),          # 0-100, higher = riskier
            "spi": s.get("spi"),                                # computed from activities
            "progress_pct": s.get("progress_pct"),
            "schedule_status": s.get("schedule_status"),
            "activities_behind": s.get("activities_behind"),
            "critical_activities": s.get("critical_activities"),
            "procurement_risk_pct": r.get("procurement", {}).get("procurement_risk_pct"),
            "execution_risk_pct": r.get("execution", {}).get("execution_risk_pct"),
            "health_score": r.get("health", {}).get("health_score"),
            "risk_drivers": ov.get("components"),
        })
    return {
        "total_portfolio_projects": len(kpis),
        "showing_top_n": top_n,
        "riskiest_projects": riskiest,
        "_note": "P6 SPI is retained when available and is not replaced with an activity-count proxy.",
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
    
    name_or_id = name_or_id.strip()
    
    def _build_result(mapping):
        return {
            "project_id": mapping.project_id,
            "project_name": mapping.project_name_from_p6 or mapping.project or mapping.project_id,
            "p6_name": mapping.project_name_from_p6 or "",
            "spv_name": mapping.spv_name or "",
            "category": mapping.category or "",
            "capacity_mwac": mapping.capacity_mwac,
        }
    
    # Direct project_id match
    m = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_id == name_or_id
    ).first()
    if m:
        return _build_result(m)
    
    # Match against project_mapping.project
    m = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project == name_or_id
    ).first()
    if m and m.project_id:
        return _build_result(m)
    
    # Match against P6 project name
    p6 = db.query(models.P6Project).filter(
        models.P6Project.name == name_or_id
    ).first()
    if p6:
        m = db.query(models.ProjectMapping).filter(
            models.ProjectMapping.project_id == p6.project_id
        ).first()
        if m:
            return _build_result(m)
    
    # Match project_name_from_p6
    m = db.query(models.ProjectMapping).filter(
        models.ProjectMapping.project_name_from_p6 == name_or_id
    ).first()
    if m and m.project_id:
        return _build_result(m)
    
    # Case-insensitive fuzzy search — score every containment match and keep the best one.
    # A short code (e.g. spv_name="ARE3L") is a substring of almost every one of its own
    # projects' full names, so returning the FIRST containment hit would let an unrelated
    # project sharing that short code beat the actual near-exact name match. Score by
    # similarity ratio instead so the most specific match wins.
    name_lower = name_or_id.lower()
    all_mappings = db.query(models.ProjectMapping).all()
    MIN_SCORE = 0.4

    best_mapping = None
    best_score = 0.0
    for mapping in all_mappings:
        candidates = [
            mapping.project or "",
            mapping.project_name_from_p6 or "",
            mapping.spv_name or "",
        ]
        for candidate in candidates:
            if not candidate:
                continue
            candidate_lower = candidate.lower()
            if name_lower not in candidate_lower and candidate_lower not in name_lower:
                continue
            score = difflib.SequenceMatcher(None, name_lower, candidate_lower).ratio()
            if score > best_score:
                best_score = score
                best_mapping = mapping

    if best_mapping and best_score >= MIN_SCORE:
        return _build_result(best_mapping)
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
            "title": n.change_type,
            "message": n.message,
            "category": n.category,
            "status": n.action_status,
            "project_name": n.project_name,
            "ai_suggestion": n.ai_suggestion
        })
    return result
