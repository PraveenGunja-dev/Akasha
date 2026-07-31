"""Thin, read-only tools for canonical Pulse quality analytics.

These functions are intentionally not registered with an agent tool registry yet.
"""

from sqlalchemy.orm import Session

from services.quality_analytics_service import QualityAnalyticsService


def quality_get_portfolio_overview(db: Session, portfolio: str | None = None) -> dict:
    """Get portfolio NC/RFI totals, closure, aging, trends, and provenance."""
    return QualityAnalyticsService.portfolio_overview(db, portfolio).to_dict()


def quality_get_project_status(
    db: Session, project: str, portfolio: str | None = None
) -> dict:
    """Resolve a project and get its canonical quality snapshot."""
    result = QualityAnalyticsService.project_status(db, project, portfolio).to_dict()
    result.pop("candidates", None)
    for warning in result.get("warnings", []):
        warning.pop("candidates", None)
    return result


def quality_get_contractor_scorecard(
    db: Session, portfolio: str | None = None
) -> dict:
    """Get contractor quality scores using the dashboard formula."""
    return QualityAnalyticsService.contractor_scorecard(db, portfolio).to_dict()


def quality_list_ncs(
    db: Session,
    *,
    status: str | None = None,
    category: str | None = None,
    cluster: str | None = None,
    project: str | None = None,
    package: str | None = None,
    portfolio: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """List normalized NCs with optional quality and project scope filters."""
    return QualityAnalyticsService.list_ncs(
        db,
        status=status,
        category=category,
        cluster=cluster,
        project=project,
        package=package,
        portfolio=portfolio,
        page=page,
        page_size=page_size,
    ).to_dict()
